# Secrets, APIs and Accounts Checklist

## Required (minimum to run)
| Item | Env var | Where to get | Cost |
|---|---|---|---|
| Gemini API key | `GOOGLE_API_KEY` | aistudio.google.com, "Get API key" | Free tier |

## Required for full (non-demo) mode
| Item | Env var | Where to get | Cost |
|---|---|---|---|
| Google Cloud project | `GOOGLE_CLOUD_PROJECT` | console.cloud.google.com | Free credits |
| Maps Platform key (enable Routes API, Geocoding API) | `GOOGLE_MAPS_API_KEY` | Cloud Console, APIs and Services, Credentials | Free monthly credit, needs billing account |
| Firestore database (Native mode) | uses ADC / service account | Cloud Console, Firestore | Free tier |
| Service account JSON (local only) | `GOOGLE_APPLICATION_CREDENTIALS` | IAM, Service Accounts | Free |
| Telegram bot token | `TELEGRAM_BOT_TOKEN` | Telegram, chat with @BotFather, `/newbot` | Free |
| Dispatcher Telegram chat ID | `TELEGRAM_DISPATCHER_CHAT_ID` | message the bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` | Free |
| Cloud Storage bucket (POD photos) | `GCS_BUCKET` | Cloud Console, Storage | Free tier |

## No key needed
- Open-Meteo weather API
- OR-Tools (pip package)

## Optional
| Item | Env var | Use |
|---|---|---|
| Fallback Gemini model | `GEMINI_FALLBACK_MODEL` | used on rate limit |
| Twilio WhatsApp sandbox | `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_WHATSAPP_FROM` | P1 only, skip unless time remains |

## Accounts and setup tasks
- [ ] GitHub public repo created, all team members added
- [ ] Google Cloud project + billing enabled (credits)
- [ ] Enable APIs: Routes API, Geocoding API, Firestore, Cloud Run, Cloud Build, Cloud Storage
- [ ] Gemini key from AI Studio
- [ ] Telegram bot created, 1 dispatcher test chat, 1 driver test chat, 1 customer test chat
- [ ] Restrict Maps key by API (Routes, Geocoding) and set a quota cap
- [ ] Store prod secrets in Secret Manager, never in repo
- [ ] Add `.env` to `.gitignore` before first commit

## Cloud Run secrets
```
gcloud run deploy dispatchmind --source . --region asia-south1 \
  --set-env-vars DEMO_MODE=false \
  --set-secrets GOOGLE_API_KEY=gemini-key:latest,GOOGLE_MAPS_API_KEY=maps-key:latest,TELEGRAM_BOT_TOKEN=tg-token:latest
```
