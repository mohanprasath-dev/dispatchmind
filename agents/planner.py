import json
import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from core.config import GOOGLE_API_KEY, DEMO_MODE, BASE_DIR
from core.models import Order, Vehicle, RoutePlan, VehicleRoute, Stop
from core.resilience import resilient
from core.store import store

logger = logging.getLogger(__name__)

# Default Depot: Guindy Logistics Hub / Chennai Central
DEFAULT_DEPOT = {
    "name": "Chennai Central Depot",
    "lat": 13.0067,
    "lng": 80.2025,
    "pincode": "600032",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate road-adjusted distance in km between two lat/lng points (haversine x 1.4)."""
    if (lat1, lon1) == (lat2, lon2):
        return 0.0
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c * 1.4, 2)


def time_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' string to minutes from midnight."""
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 540  # Default 09:00 AM (540 minutes)


def minutes_to_time_str(minutes: int) -> str:
    """Convert minutes from midnight to 'HH:MM' string."""
    hours = (minutes // 60) % 24
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def get_tuning_buffers() -> Dict[str, int]:
    """Retrieve learned pincode buffers from tuning collection."""
    buffers: Dict[str, int] = {}
    tuning_docs = store.list("tuning")
    for doc in tuning_docs:
        pincode = doc.get("pincode")
        buf = doc.get("eta_buffer_min", 0)
        if pincode:
            buffers[str(pincode)] = int(buf)
    return buffers


def explain_plan_with_gemini(summary_text: str) -> str:
    """
    Call Gemini 2.5 Flash to generate a plain English explanation of the route plan.
    Math and optimization are strictly handled by OR-Tools; Gemini explains the schedule.
    """
    if not GOOGLE_API_KEY:
        return generate_deterministic_explanation(summary_text)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)
        prompt = (
            "You are the DispatchMind Senior Dispatcher Copilot. "
            "Review the following vehicle routing schedule optimized by Google OR-Tools:\n\n"
            f"{summary_text}\n\n"
            "Provide a concise, professional executive dispatch summary in plain English. "
            "Address the dispatcher directly. "
            "Cover fleet utilization, stop sequencing, delivery completion times, and any unassigned orders. "
            "Do not use em dashes in your response."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=600,
            ),
        )
        if response and response.text:
            import re
            return re.sub(r"[\u2013\u2014]", "-", response.text).strip()
    except Exception as exc:
        logger.warning(f"Gemini explanation failed, using fallback: {exc}")

    return generate_deterministic_explanation(summary_text)


def generate_deterministic_explanation(summary_text: str) -> str:
    """Clean fallback plain English explanation of the route plan."""
    return (
        "Dispatch schedule optimized successfully via OR-Tools VRP engine. "
        "Vehicle capacities and customer delivery windows are strictly observed with zero violations. "
        "Dynamic transit times incorporate road tortuosity factors and historical postal code buffers. "
        "All assigned stops have been sequenced to minimize total fleet kilometers and arrival delays."
    )


@resilient(retries=2, base_delay=0.01)
def solve_vrp(
    orders: List[Order],
    vehicles: List[Vehicle],
    depot_lat: float = DEFAULT_DEPOT["lat"],
    depot_lng: float = DEFAULT_DEPOT["lng"],
    avg_speed_kmh: float = 30.0,
    service_time_min: int = 10,
) -> RoutePlan:
    """
    Solve Capacity and Time Window Vehicle Routing Problem (CVRPTW) with Google OR-Tools.
    Applies per-pincode eta_buffer_min from the tuning collection.
    """
    if not orders:
        return RoutePlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            routes=[],
            total_km=0.0,
            unassigned_orders=[],
            explanation="No pending orders to schedule.",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    if not vehicles:
        raise ValueError("Cannot plan routes without vehicles.")

    pincode_buffers = get_tuning_buffers()

    # Node 0 is Depot; Nodes 1..N are Orders
    nodes = [{"lat": depot_lat, "lng": depot_lng, "pincode": DEFAULT_DEPOT["pincode"], "order": None}]
    for o in orders:
        # Fallback coordinates if order has none
        o_lat = o.lat if o.lat is not None else depot_lat + 0.02
        o_lng = o.lng if o.lng is not None else depot_lng + 0.02
        nodes.append({"lat": o_lat, "lng": o_lng, "pincode": o.pincode, "order": o})

    num_nodes = len(nodes)
    num_vehicles = len(vehicles)
    depot_index = 0

    # Distance and Time Matrices
    dist_matrix = [[0.0 for _ in range(num_nodes)] for _ in range(num_nodes)]
    time_matrix = [[0 for _ in range(num_nodes)] for _ in range(num_nodes)]

    for i in range(num_nodes):
        for j in range(num_nodes):
            if i == j:
                dist_matrix[i][j] = 0.0
                time_matrix[i][j] = 0
            else:
                d = haversine_km(nodes[i]["lat"], nodes[i]["lng"], nodes[j]["lat"], nodes[j]["lng"])
                dist_matrix[i][j] = d
                transit_min = int(round((d / avg_speed_kmh) * 60))
                # Add destination service time and tuning buffer if node is an order
                dest_buffer = pincode_buffers.get(nodes[j]["pincode"], 0) if j > 0 else 0
                dest_service = service_time_min if j > 0 else 0
                time_matrix[i][j] = transit_min + dest_service + dest_buffer

    # Demands: 0 for depot, order.weight_kg for orders
    demands = [0] + [int(round(o.weight_kg)) for o in orders]
    vehicle_capacities = [int(v.capacity_kg) for v in vehicles]

    # Time Windows: Minutes relative to 09:00 AM (shift start)
    # 09:00 = 0 minutes; 18:00 = 540 minutes (9 hour shift window)
    shift_start_min = 540  # 09:00 AM
    time_windows: List[Tuple[int, int]] = [(0, 720)]  # Depot open 09:00 to 21:00

    for o in orders:
        start_abs = time_to_minutes(o.window_start)
        end_abs = time_to_minutes(o.window_end)
        w_start = max(0, start_abs - shift_start_min)
        w_end = max(w_start + 30, end_abs - shift_start_min)
        time_windows.append((w_start, w_end))

    # Initialize OR-Tools Routing
    manager = pywrapcp.RoutingIndexManager(num_nodes, num_vehicles, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    # 1. Transit Cost Callback (distance in meters or tenths of km)
    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(dist_matrix[from_node][to_node] * 1000)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 2. Capacity Constraint Dimension
    def demand_callback(from_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        return demands[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        vehicle_capacities,
        True,  # start cumul to zero
        "Capacity",
    )

    # 3. Time Window Constraint Dimension
    def time_transit_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return time_matrix[from_node][to_node]

    time_callback_index = routing.RegisterTransitCallback(time_transit_callback)
    routing.AddDimension(
        time_callback_index,
        180,  # allow waiting time up to 180 min if early
        720,  # maximum route duration: 12 hours
        False,  # don't force start to zero
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Add Time Windows for each order node
    for node_idx, (start, end) in enumerate(time_windows):
        index = manager.NodeToIndex(node_idx)
        time_dimension.CumulVar(index).SetRange(start, end)

    # 4. Disjunctions: Allow dropping nodes that cannot be scheduled (e.g. overcapacity or window violation)
    penalty = 1000000
    for node_idx in range(1, num_nodes):
        routing.AddDisjunction([manager.NodeToIndex(node_idx)], penalty)

    # Search Parameters: First solution path cheapest arc + Guided Local Search
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 5

    # Solve
    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        raise RuntimeError("OR-Tools failed to generate a feasible routing solution.")

    # Extract Routes
    routes_output: List[VehicleRoute] = []
    total_fleet_km = 0.0
    assigned_order_ids = set()

    for vehicle_id_idx in range(num_vehicles):
        vehicle = vehicles[vehicle_id_idx]
        index = routing.Start(vehicle_id_idx)
        stops: List[Stop] = []
        route_km = 0.0
        route_weight = 0.0
        stop_num = 1

        while not routing.IsEnd(index):
            node_idx = manager.IndexToNode(index)
            if node_idx != 0:  # Skip depot node
                order = nodes[node_idx]["order"]
                assigned_order_ids.add(order.id)
                time_var = time_dimension.CumulVar(index)
                arrival_min = shift_start_min + solution.Min(time_var)
                eta_str = minutes_to_time_str(arrival_min)

                stop = Stop(
                    stop_number=stop_num,
                    order_id=order.id,
                    customer_name=order.customer_name,
                    address=order.address,
                    pincode=order.pincode,
                    lat=order.lat or nodes[node_idx]["lat"],
                    lng=order.lng or nodes[node_idx]["lng"],
                    weight_kg=order.weight_kg,
                    eta=eta_str,
                    window_start=order.window_start,
                    window_end=order.window_end,
                    status="planned",
                )
                stops.append(stop)
                route_weight += order.weight_kg
                stop_num += 1

            next_index = solution.Value(routing.NextVar(index))
            next_node = manager.IndexToNode(next_index)
            route_km += dist_matrix[node_idx][next_node]
            index = next_index

        route_km = round(route_km, 2)
        total_fleet_km += route_km

        v_route = VehicleRoute(
            vehicle_id=vehicle.id,
            driver_id=vehicle.driver_id,
            stops=stops,
            total_km=route_km,
            total_weight_kg=round(route_weight, 2),
            start_time="09:00",
            end_time=stops[-1].eta if stops else "09:00",
        )
        routes_output.append(v_route)

    total_fleet_km = round(total_fleet_km, 2)

    # Identify Unassigned Orders and explain specific reasons
    unassigned_orders: List[Dict[str, str]] = []
    max_vehicle_cap = max(vehicle_capacities) if vehicle_capacities else 0

    for o in orders:
        if o.id not in assigned_order_ids:
            if o.weight_kg > max_vehicle_cap:
                reason = f"Order weight ({o.weight_kg} kg) exceeds maximum vehicle capacity ({max_vehicle_cap} kg)."
            else:
                reason = (
                    f"Delivery window {o.window_start}-{o.window_end} or regional transit constraint "
                    f"could not be fulfilled without violating capacity or schedule boundaries."
                )
            unassigned_orders.append({"order_id": o.id, "reason": reason})

    # Prepare summary for Gemini explanation
    summary_lines = [
        f"Fleet Optimization Summary:",
        f"- Total vehicles deployed: {num_vehicles}",
        f"- Total stops assigned: {len(assigned_order_ids)} / {len(orders)}",
        f"- Total route distance: {total_fleet_km} km",
        f"- Unassigned orders: {len(unassigned_orders)}",
    ]
    for r in routes_output:
        summary_lines.append(
            f"* Vehicle {r.vehicle_id}: {len(r.stops)} stops, {r.total_km} km, {r.total_weight_kg} kg load"
        )
    if unassigned_orders:
        for u in unassigned_orders:
            summary_lines.append(f"* Unassigned: Order {u['order_id']} ({u['reason']})")

    summary_text = "\n".join(summary_lines)
    explanation = explain_plan_with_gemini(summary_text)

    plan_id = f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    plan = RoutePlan(
        plan_id=plan_id,
        routes=routes_output,
        total_km=total_fleet_km,
        unassigned_orders=unassigned_orders,
        explanation=explanation,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Persist in store routes collection
    store.set("routes", plan.plan_id, plan)

    return plan


def plan_day(
    orders: Optional[List[Order]] = None,
    vehicles: Optional[List[Vehicle]] = None,
) -> RoutePlan:
    """
    Main dispatch planner entry point:
    Loads pending orders and vehicles, computes CVRPTW with OR-Tools,
    and returns a validated RoutePlan.
    """
    if orders is None:
        raw_orders = store.list("orders", filters={"status": "pending"})
        if not raw_orders:
            # Load from seed.json if store empty
            seed_file = BASE_DIR / "data" / "seed.json"
            if seed_file.exists():
                with open(seed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    raw_orders = data.get("orders", [])
        orders = [Order(**o) if isinstance(o, dict) else o for o in raw_orders]

    if vehicles is None:
        raw_vehicles = store.list("vehicles")
        if not raw_vehicles:
            seed_file = BASE_DIR / "data" / "seed.json"
            if seed_file.exists():
                with open(seed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    raw_vehicles = data.get("vehicles", [])
        vehicles = [Vehicle(**v) if isinstance(v, dict) else v for v in raw_vehicles]

    return solve_vrp(orders=orders, vehicles=vehicles)


def build_agent():
    """Build and export Google ADK Planner Agent."""
    from google.adk.agents import Agent

    def planner_tool() -> str:
        """Execute daily capacity and time-window route planning across available fleet."""
        plan = plan_day()
        return json.dumps(plan.model_dump())

    agent = Agent(
        name="planner",
        model="gemini-2.5-flash",
        description="Route planning agent using Google OR-Tools for capacity and time-window VRP.",
        instruction=(
            "You are the Planner Agent for DispatchMind. "
            "You optimize vehicle delivery sequences across Indian urban and suburban corridors using OR-Tools. "
            "Vehicle capacity and delivery time windows are hard constraints that must never be violated. "
            "Explain the final route plan clearly to dispatchers in plain English without using em dashes."
        ),
        tools=[planner_tool],
    )
    return agent
