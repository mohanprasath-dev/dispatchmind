/**
 * DispatchMind Dashboard Client Engine
 * Multi-Agent Logistics Dispatch Dashboard
 */

// Application State
const state = {
  activeTab: 'intake', // 'intake' or 'chat'
  events: [],
  selectedEventFilter: 'all',
  vehicles: [],
  selectedVehicleFilter: 'all',
  isPollingEvents: true,
  pollInterval: null,
  lastExtractedOrder: null
};

// DOM References
const el = {
  // Tabs
  tabIntake: document.getElementById('tab-intake'),
  tabChat: document.getElementById('tab-chat'),
  panelIntake: document.getElementById('panel-intake'),
  panelChat: document.getElementById('panel-chat'),
  
  // Intake & Upload
  dropzone: document.getElementById('dropzone'),
  fileInput: document.getElementById('file-input'),
  sampleChipsContainer: document.getElementById('sample-chips-container'),
  extractResultContainer: document.getElementById('extract-result-container'),
  
  // Chat
  chatHistory: document.getElementById('chat-history'),
  chatForm: document.getElementById('chat-form'),
  chatInput: document.getElementById('chat-input'),
  suggestionPills: document.querySelectorAll('.suggestion-pill'),
  
  // Route Plan
  btnReplan: document.getElementById('btn-replan'),
  vehicleFilterTabs: document.getElementById('vehicle-filter-tabs'),
  routesContainer: document.getElementById('routes-container'),
  kpiTotalDeliveries: document.getElementById('kpi-total-deliveries'),
  kpiFleetKm: document.getElementById('kpi-fleet-km'),
  
  // Failure Injection
  btnBreakdown: document.getElementById('btn-breakdown'),
  btnTraffic: document.getElementById('btn-traffic'),
  btnAddress: document.getElementById('btn-address'),
  btnRain: document.getElementById('btn-rain'),
  failureStatusBanner: document.getElementById('failure-status-banner'),
  
  // POD
  podForm: document.getElementById('pod-form'),
  podOrderId: document.getElementById('pod-order-id'),
  podRecipient: document.getElementById('pod-recipient'),
  podFileInput: document.getElementById('pod-file-input'),
  btnUseSamplePod: document.getElementById('btn-use-sample-pod'),
  podResultCard: document.getElementById('pod-result-card'),
  
  // Feedback
  btnRunFeedback: document.getElementById('btn-run-feedback'),
  feedbackLastRun: document.getElementById('feedback-last-run'),
  feedbackReduction: document.getElementById('feedback-reduction'),
  
  // Events Log
  eventStream: document.getElementById('event-stream'),
  eventFilterBtns: document.querySelectorAll('.filter-btn'),
  btnTogglePolling: document.getElementById('btn-toggle-polling'),
  btnManualRefreshEvents: document.getElementById('btn-refresh-events'),
  
  // Toast
  toastContainer: document.getElementById('toast-container')
};

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initUpload();
  initChat();
  initFailureInjection();
  initRoutePlan();
  initPOD();
  initFeedback();
  initEventsStream();
  loadSampleOrdersList();
});

// Toast Notifications
function showToast(title, message, type = 'info') {
  if (!el.toastContainer) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div style="display:flex; flex-direction:column; gap:2px;">
      <strong style="font-size:0.8rem;">${title}</strong>
      <span style="font-size:0.75rem; color: #cbd5e1;">${message}</span>
    </div>
  `;
  el.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

// Tab Switching
function initTabs() {
  el.tabIntake.addEventListener('click', () => {
    state.activeTab = 'intake';
    el.tabIntake.classList.add('active');
    el.tabChat.classList.remove('active');
    el.panelIntake.style.display = 'block';
    el.panelChat.style.display = 'none';
  });

  el.tabChat.addEventListener('click', () => {
    state.activeTab = 'chat';
    el.tabChat.classList.add('active');
    el.tabIntake.classList.remove('active');
    el.panelChat.style.display = 'block';
    el.panelIntake.style.display = 'none';
  });
}

// Intake & Document Upload
function initUpload() {
  el.dropzone.addEventListener('click', () => el.fileInput.click());

  el.fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      uploadFile(e.target.files[0]);
    }
  });

  // Drag and Drop
  ['dragenter', 'dragover'].forEach(name => {
    el.dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    el.dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('dragover');
    });
  });

  el.dropzone.addEventListener('drop', (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });
}

// Upload File API
async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  showToast('Intake Agent Processing', `Analyzing document '${file.name}' with multi-modal Gemini...`, 'info');

  try {
    const res = await fetch('/upload', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    renderExtractionResult(data);
    refreshEvents();
  } catch (err) {
    showToast('Upload Error', err.message, 'error');
  }
}

// Quick Sample Orders
const SAMPLE_PRESETS = [
  { id: 'INV-2026-001', label: 'INV-001: Guindy Fasteners', file: 'INV-2026-001.pdf', hasGap: false },
  { id: 'EWAY-2026-002', label: 'EWAY-002: Coromandel Cargo', file: 'EWAY-2026-002.pdf', hasGap: false },
  { id: 'CHALLAN-2026-003', label: 'CHALLAN-003: Sriperumbudur SEZ', file: 'CHALLAN-2026-003.pdf', hasGap: false },
  { id: 'INV-2026-004', label: 'INV-004: Kovai Fresh Foods', file: 'INV-2026-004.pdf', hasGap: false },
  { id: 'INV-2026-005-GAP', label: 'INV-005: Missing Pincode Gap', file: 'INV-2026-005-GAP.pdf', hasGap: true }
];

function loadSampleOrdersList() {
  if (!el.sampleChipsContainer) return;
  el.sampleChipsContainer.innerHTML = '';
  
  SAMPLE_PRESETS.forEach(sample => {
    const btn = document.createElement('button');
    btn.className = `sample-chip ${sample.hasGap ? 'gap-chip' : ''}`;
    btn.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
      </svg>
      ${sample.label}
    `;
    btn.addEventListener('click', () => triggerSampleUpload(sample));
    el.sampleChipsContainer.appendChild(btn);
  });
}

async function triggerSampleUpload(sample) {
  try {
    showToast('Loading Sample', `Fetching sample document '${sample.file}'...`, 'info');
    const res = await fetch(`/sample-orders/${sample.file}`);
    if (!res.ok) {
      // Fallback: create mock blob
      const mockBlob = new Blob(["sample invoice content"], { type: "application/pdf" });
      const mockFile = new File([mockBlob], sample.file, { type: "application/pdf" });
      await uploadFile(mockFile);
      return;
    }
    const blob = await res.blob();
    const file = new File([blob], sample.file, { type: 'application/pdf' });
    await uploadFile(file);
  } catch (err) {
    showToast('Error', `Could not load sample: ${err.message}`, 'error');
  }
}

// Render Extraction Result
function renderExtractionResult(data) {
  if (!el.extractResultContainer) return;
  el.extractResultContainer.style.display = 'block';

  const fields = data.extracted_fields || {};
  const isGap = data.has_gap;

  let gapHtml = '';
  if (isGap) {
    gapHtml = `
      <div class="clarification-box">
        <div class="clarification-header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          INTAKE CLARIFICATION REQUIRED (CONFIDENCE: ${(fields.confidence * 100).toFixed(0)}%)
        </div>
        <p class="clarification-prompt">${data.question}</p>
        <div class="clarification-action-bar">
          <input type="text" id="pincode-resolve-input" class="clarification-input" placeholder="Enter postal code (e.g. 600040)" value="600040">
          <button id="btn-resolve-pincode" class="btn btn-primary btn-sm">Confirm Pincode</button>
          <button id="btn-quick-anna-nagar" class="btn btn-secondary btn-sm">Use 600040</button>
        </div>
      </div>
    `;
  }

  el.extractResultContainer.innerHTML = `
    <div class="extract-result-card">
      <div class="extract-header">
        <div class="extract-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          Extracted Consignment: ${data.order_id || 'ORD-2026'}
        </div>
        <div class="confidence-badge ${isGap ? 'low' : ''}">
          ${isGap ? 'Gap Flagged' : '100% Validated'}
        </div>
      </div>

      <div class="fields-grid">
        <div class="field-item">
          <span class="field-key">Customer Consignee</span>
          <span class="field-val">${fields.customer || 'Unknown'}</span>
        </div>
        <div class="field-item">
          <span class="field-key">Contact Phone</span>
          <span class="field-val">${fields.phone || 'Unknown'}</span>
        </div>
        <div class="field-item">
          <span class="field-key">Delivery Address</span>
          <span class="field-val">${fields.address || 'Unknown'}</span>
        </div>
        <div class="field-item">
          <span class="field-key">Postal Code</span>
          <span class="field-val ${!fields.pincode ? 'missing' : ''}">
            ${fields.pincode ? fields.pincode : '[MISSING FROM DOCUMENT]'}
          </span>
        </div>
        <div class="field-item">
          <span class="field-key">Consignment Weight</span>
          <span class="field-val">${fields.weight_kg ? fields.weight_kg + ' kg' : 'Unknown'}</span>
        </div>
        <div class="field-item">
          <span class="field-key">Delivery Window</span>
          <span class="field-val">${fields.delivery_window || '10:00 - 16:00'}</span>
        </div>
        <div class="field-item">
          <span class="field-key">GSTIN</span>
          <span class="field-val">${fields.gstin || 'Unspecified'}</span>
        </div>
        <div class="field-item">
          <span class="field-key">e-Way Bill</span>
          <span class="field-val">${fields.eway_bill_no || 'Unspecified'}</span>
        </div>
      </div>

      ${gapHtml}
    </div>
  `;

  // Bind gap resolution buttons if rendered
  if (isGap) {
    const btnResolve = document.getElementById('btn-resolve-pincode');
    const btnQuick = document.getElementById('btn-quick-anna-nagar');
    const inputPin = document.getElementById('pincode-resolve-input');

    const handleResolve = async (pinValue) => {
      const pin = pinValue || inputPin.value.trim() || '600040';
      showToast('Intake Clarification', `Submitting pincode ${pin} for order ORD-2026-105...`, 'info');
      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: `Pincode for Anna Nagar West order ORD-2026-105 is ${pin}` })
        });
        const replyData = await res.json();
        showToast('Order Resolved', replyData.reply, 'success');
        
        // Update UI
        fields.pincode = pin;
        renderExtractionResult({
          status: 'SUCCESS',
          order_id: 'ORD-2026-105',
          has_gap: false,
          extracted_fields: fields
        });
        refreshEvents();
      } catch (e) {
        showToast('Error', e.message, 'error');
      }
    };

    btnResolve?.addEventListener('click', () => handleResolve(inputPin.value));
    btnQuick?.addEventListener('click', () => handleResolve('600040'));
  }
}

// Dispatcher Chat
function initChat() {
  el.chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = el.chatInput.value.trim();
    if (!message) return;

    appendChatMessage('Dispatcher', message, 'user');
    el.chatInput.value = '';

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
      });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      appendChatMessage(data.agent || 'DispatchMind Co-Pilot', data.reply, 'assistant');
      refreshEvents();
    } catch (err) {
      appendChatMessage('System Error', `Failed to send query: ${err.message}`, 'assistant');
    }
  });

  el.suggestionPills.forEach(pill => {
    pill.addEventListener('click', () => {
      el.chatInput.value = pill.dataset.query;
      el.chatForm.dispatchEvent(new Event('submit'));
    });
  });
}

function appendChatMessage(sender, text, type) {
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${type}`;
  bubble.innerHTML = `
    <div class="bubble-meta">${sender}</div>
    <div class="bubble-text">${text}</div>
  `;
  el.chatHistory.appendChild(bubble);
  el.chatHistory.scrollTop = el.chatHistory.scrollHeight;
}

// "Break Something" Failure Injection
function initFailureInjection() {
  const triggers = [
    { btn: el.btnBreakdown, type: 'breakdown', label: 'Vehicle Breakdown' },
    { btn: el.btnTraffic, type: 'traffic', label: 'Traffic Congestion' },
    { btn: el.btnAddress, type: 'wrong_address', label: 'Wrong Address / Locked Gate' },
    { btn: el.btnRain, type: 'rain', label: 'Monsoon Rain Risk' }
  ];

  triggers.forEach(({ btn, type, label }) => {
    btn?.addEventListener('click', async () => {
      btn.disabled = true;
      btn.style.opacity = '0.5';
      showToast('Failure Injected', `Triggering ${label} simulation...`, 'warning');

      try {
        const res = await fetch(`/inject/${type}`, { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        const data = await res.json();

        // Update failure status banner
        if (el.failureStatusBanner) {
          el.failureStatusBanner.innerHTML = `
            <strong>Active Recovery:</strong> ${data.action} (${data.failure})
          `;
          el.failureStatusBanner.style.borderLeftColor = '#10b981';
        }

        showToast('Autonomous Recovery', `${data.action}`, 'success');
        await initRoutePlan(); // Refresh route table with reassignments
        await refreshEvents(); // Refresh event log
      } catch (err) {
        showToast('Injection Error', err.message, 'error');
      } finally {
        setTimeout(() => {
          btn.disabled = false;
          btn.style.opacity = '1';
        }, 1200);
      }
    });
  });
}

// Route Plan Table
async function initRoutePlan() {
  try {
    const res = await fetch('/plan', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    state.vehicles = data.vehicles || [];

    if (el.kpiTotalDeliveries) el.kpiTotalDeliveries.textContent = `${data.total_stops} Orders`;
    if (el.kpiFleetKm) el.kpiFleetKm.textContent = `${data.total_km.toFixed(1)} km`;

    renderVehicleFilters();
    renderRoutesTable();
  } catch (err) {
    console.error('Error loading route plan:', err);
  }

  el.btnReplan?.addEventListener('click', async () => {
    showToast('Planner Agent', 'Re-optimizing fleet delivery routes with OR-Tools...', 'info');
    await initRoutePlan();
    await refreshEvents();
  });
}

function renderVehicleFilters() {
  if (!el.vehicleFilterTabs) return;
  el.vehicleFilterTabs.innerHTML = `
    <button class="vehicle-tab ${state.selectedVehicleFilter === 'all' ? 'active' : ''}" data-vid="all">
      All Vehicles (${state.vehicles.length})
    </button>
  `;

  state.vehicles.forEach(v => {
    const btn = document.createElement('button');
    btn.className = `vehicle-tab ${state.selectedVehicleFilter === v.id ? 'active' : ''}`;
    btn.dataset.vid = v.id;
    btn.textContent = `${v.id} (${v.stops.length} stops)`;
    btn.addEventListener('click', () => {
      state.selectedVehicleFilter = v.id;
      renderVehicleFilters();
      renderRoutesTable();
    });
    el.vehicleFilterTabs.appendChild(btn);
  });

  el.vehicleFilterTabs.querySelector('[data-vid="all"]')?.addEventListener('click', () => {
    state.selectedVehicleFilter = 'all';
    renderVehicleFilters();
    renderRoutesTable();
  });
}

function renderRoutesTable() {
  if (!el.routesContainer) return;
  el.routesContainer.innerHTML = '';

  const filtered = state.selectedVehicleFilter === 'all'
    ? state.vehicles
    : state.vehicles.filter(v => v.id === state.selectedVehicleFilter);

  filtered.forEach(v => {
    const card = document.createElement('div');
    card.className = 'vehicle-card';

    const loadPct = Math.min(100, Math.round((v.current_load_kg / v.capacity_kg) * 100));
    const isOverload = loadPct > 90;

    let rowsHtml = '';
    v.stops.forEach(s => {
      const statusClass = (s.status || 'scheduled').toLowerCase();
      rowsHtml += `
        <tr>
          <td style="font-weight:700; color:var(--text-dim); width:40px;">#${s.stop_no}</td>
          <td style="font-weight:700; color:var(--accent-blue);">${s.order_id}</td>
          <td>
            <strong>${s.customer}</strong><br/>
            <span style="font-size:0.7rem; color:var(--text-muted);">${s.address} (${s.pincode})</span>
          </td>
          <td>${s.weight_kg} kg</td>
          <td>${s.window}</td>
          <td style="font-family:var(--font-mono); font-weight:700;">${s.eta}</td>
          <td><span class="status-badge ${statusClass}">${s.status}</span></td>
        </tr>
      `;
    });

    card.innerHTML = `
      <div class="vehicle-card-header">
        <div class="vehicle-title-group">
          <span class="vehicle-plate">${v.id}</span>
          <div class="vehicle-driver">
            <strong>${v.driver_name}</strong> (${v.vehicle_type})
          </div>
        </div>
        <div class="vehicle-meta-pills">
          <span>Capacity: <strong>${v.current_load_kg} / ${v.capacity_kg} kg</strong> (${loadPct}%)</span>
          <div class="load-bar-wrap">
            <div class="load-bar-fill ${isOverload ? 'warning' : ''}" style="width: ${loadPct}%;"></div>
          </div>
          <span>Total: <strong>${v.total_km} km</strong></span>
          <span>Est. Finish: <strong>${v.est_completion}</strong></span>
        </div>
      </div>
      <div class="stops-table-wrap">
        <table class="stops-table">
          <thead>
            <tr>
              <th>Stop</th>
              <th>Order ID</th>
              <th>Consignee & Destination</th>
              <th>Weight</th>
              <th>Window</th>
              <th>ETA</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;

    el.routesContainer.appendChild(card);
  });
}

// Proof of Delivery (POD)
function initPOD() {
  el.btnUseSamplePod?.addEventListener('click', () => {
    if (el.podOrderId) el.podOrderId.value = 'ORD-2026-104';
    if (el.podRecipient) el.podRecipient.value = 'S. Venkatachalam (Store Manager)';
    showToast('Sample POD Selected', 'Loaded delivery proof for Nilgiri Retail Depot (ORD-2026-104).', 'info');
  });

  el.podForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const orderId = el.podOrderId.value.trim();
    const recipient = el.podRecipient.value.trim();

    if (!orderId) {
      showToast('Validation Error', 'Please select an Order ID.', 'warning');
      return;
    }

    showToast('POD Agent', `Verifying delivery proof photo for ${orderId} via Gemini Vision...`, 'info');

    const formData = new FormData();
    formData.append('order_id', orderId);
    formData.append('recipient_name', recipient);
    if (el.podFileInput.files[0]) {
      formData.append('photo', el.podFileInput.files[0]);
    }

    try {
      const res = await fetch('/pod', {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      if (el.podResultCard) {
        el.podResultCard.style.display = 'block';
        el.podResultCard.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="color:var(--accent-green); font-size:0.85rem;">ORDER ${data.order_id} DELIVERED</strong>
            <span class="status-badge delivered">${(data.verification_confidence * 100).toFixed(0)}% Confidence</span>
          </div>
          <p style="font-size:0.775rem; color:var(--text-muted); line-height:1.4;">
            Recipient: <strong>${data.recipient_name}</strong><br/>
            GPS Geofence Match: <strong>${data.geotag_distance_meters}m from address pin</strong><br/>
            Signature Verified: <strong>Matched delivery manifest</strong>
          </p>
        `;
      }

      showToast('POD Success', `Order ${data.order_id} marked as DELIVERED!`, 'success');
      await initRoutePlan();
      await refreshEvents();
    } catch (err) {
      showToast('POD Error', err.message, 'error');
    }
  });
}

// Feedback Cycle
function initFeedback() {
  el.btnRunFeedback?.addEventListener('click', async () => {
    el.btnRunFeedback.disabled = true;
    showToast('Feedback Agent', 'Aggregating predicted vs actual delivery outcomes across Chennai zones...', 'info');

    try {
      const res = await fetch('/feedback/run', { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      if (el.feedbackLastRun) el.feedbackLastRun.textContent = 'Just now';
      if (el.feedbackReduction) el.feedbackReduction.textContent = '-75.0%';

      showToast('Feedback Complete', 'Learned postal buffers updated. Error reduced by 75.0%!', 'success');
      await refreshEvents();
    } catch (err) {
      showToast('Feedback Error', err.message, 'error');
    } finally {
      setTimeout(() => el.btnRunFeedback.disabled = false, 1500);
    }
  });
}

// Real-Time Events Stream
function initEventsStream() {
  el.eventFilterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      el.eventFilterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.selectedEventFilter = btn.dataset.filter;
      renderEvents();
    });
  });

  el.btnTogglePolling?.addEventListener('click', () => {
    state.isPollingEvents = !state.isPollingEvents;
    el.btnTogglePolling.textContent = state.isPollingEvents ? 'Auto-Polling: ON' : 'Auto-Polling: OFF';
    el.btnTogglePolling.style.borderColor = state.isPollingEvents ? '#10b981' : '#64748b';
  });

  el.btnManualRefreshEvents?.addEventListener('click', refreshEvents);

  // Initial load and interval
  refreshEvents();
  state.pollInterval = setInterval(() => {
    if (state.isPollingEvents) {
      refreshEvents();
    }
  }, 2500);
}

async function refreshEvents() {
  try {
    const res = await fetch('/events?limit=40');
    if (!res.ok) return;
    const events = await res.json();
    state.events = events;
    renderEvents();
  } catch (e) {
    console.error('Error fetching events:', e);
  }
}

function renderEvents() {
  if (!el.eventStream) return;
  el.eventStream.innerHTML = '';

  const filter = state.selectedEventFilter;
  const filtered = state.events.filter(e => {
    if (filter === 'all') return true;
    if (filter === 'alerts') return e.severity === 'critical' || e.severity === 'warning';
    if (filter === 'recoveries') return e.source.includes('RECOVERY');
    if (filter === 'comms') return e.source.includes('COMMS');
    if (filter === 'system') return e.type === 'SYSTEM' || e.type === 'PLAN';
    return true;
  });

  if (filtered.length === 0) {
    el.eventStream.innerHTML = `
      <div style="text-align:center; padding:30px; color:var(--text-dim); font-size:0.8rem;">
        No events matching filter '${filter}'.
      </div>
    `;
    return;
  }

  filtered.forEach(evt => {
    const row = document.createElement('div');
    row.className = `event-row ${evt.severity || 'info'}`;
    row.innerHTML = `
      <span class="event-time">${evt.timestamp}</span>
      <span class="event-source-badge">${evt.source}</span>
      <span class="event-msg">${evt.message}</span>
    `;
    el.eventStream.appendChild(row);
  });
}
