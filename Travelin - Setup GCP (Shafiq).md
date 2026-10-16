# Setup Google Cloud untuk Travelin

Untuk Shafiq · 15 Oktober 2026 · AI Builder Cup 2026

Jalankan semua perintah `gcloud` di **Google Cloud Shell** (shell.cloud.google.com), karena `gcloud` sudah terpasang di sana. Kerjakan berurutan dari bagian A sampai F.

> Project yang sudah dibuat: nama `travelin`, Project ID `sosro-511617`. Gunakan Project ID tersebut di semua perintah dan konfigurasi di bawah.

## A. Project dan API

Di Cloud Shell:

```bash
export PROJECT=sosro-511617
export REGION=asia-southeast2

# Pilih project yang sudah dibuat dan pastikan ID-nya benar
gcloud config set project $PROJECT
gcloud projects describe $PROJECT

gcloud billing accounts list
gcloud billing projects link $PROJECT --billing-account=<BILLING_ACCOUNT_ID>

gcloud services enable \
  aiplatform.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  firestore.googleapis.com storage.googleapis.com firebase.googleapis.com \
  places.googleapis.com maps-backend.googleapis.com apikeys.googleapis.com \
  iam.googleapis.com

gcloud firestore databases create --location=$REGION
```

Setelah itu pasang budget alert di Console → Billing → Budgets & alerts.

## B. Firebase

Lewat console.firebase.google.com:

1. **Add project**, lalu pilih project GCP bernama `travelin` (Project ID `sosro-511617`). Plan-nya otomatis jadi Blaze karena billing sudah terhubung.
2. **Authentication** → Get started → Sign-in method → aktifkan **Google**.
3. **Storage** → Get started → production mode, lokasi `asia-southeast2`. Nama bucket-nya nanti `sosro-511617.firebasestorage.app`.
4. **Project settings** → Your apps → **Add app (Web)**, nickname `travelin-web`. Simpan isi `firebaseConfig` (6 nilai).
5. **Redirect URI untuk login.** Google Cloud Console → APIs & Services → Credentials → buka *Web client (auto created by Google Service)*. Di **Authorized redirect URIs**, tambahkan `https://sosro-511617.web.app/__/auth/handler`.
6. **Map ID.** Google Maps Platform → Map management → Create Map ID, tipe JavaScript dan Vector. Simpan Map ID-nya.

## C. Service account, akses, dan secret

Di Cloud Shell, setelah bucket Storage dari langkah B.3 sudah ada:

```bash
export BUCKET=$PROJECT.firebasestorage.app
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')

gcloud iam service-accounts create travelin-api --display-name="Travelin API"
gcloud iam service-accounts create travelin-merchant --display-name="Travelin Merchant"
export API_SA=travelin-api@$PROJECT.iam.gserviceaccount.com
export MERCHANT_SA=travelin-merchant@$PROJECT.iam.gserviceaccount.com

for ROLE in roles/aiplatform.user roles/datastore.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member=serviceAccount:$API_SA --role=$ROLE --condition=None
done
gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$MERCHANT_SA \
  --role=roles/secretmanager.secretAccessor --condition=None
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=serviceAccount:$API_SA --role=roles/storage.objectAdmin

# Supaya Gemini bisa membaca video dari bucket
gcloud beta services identity create --service=aiplatform.googleapis.com
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=serviceAccount:service-$PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer
```

**API key.** Ada dua: satu untuk server, satu untuk browser.

```bash
# 1. Places API (New), hanya dipakai server
gcloud services api-keys create --display-name="travelin-places-server" \
  --api-target=service=places.googleapis.com
gcloud services api-keys list --format="table(uid,displayName)"
gcloud services api-keys get-key-string <UID_PLACES>
printf '%s' '<PLACES_KEY>' | gcloud secrets create places-api-key --data-file=-

# 2. Maps JavaScript API, dipakai browser (dibatasi per domain)
REFERRERS="https://$PROJECT.web.app/*,https://$PROJECT.firebaseapp.com/*"
REFERRERS="$REFERRERS,http://localhost:5173/*"
gcloud services api-keys create --display-name="travelin-maps-browser" \
  --api-target=service=maps-backend.googleapis.com \
  --allowed-referrers="$REFERRERS"
```

**Signing key untuk AP2:**

```bash
openssl ecparam -name prime256v1 -genkey -noout -out travelin-signing.pem
openssl ecparam -name prime256v1 -genkey -noout -out merchant-signing.pem
gcloud secrets create travelin-signing-key --data-file=travelin-signing.pem
gcloud secrets create merchant-signing-key --data-file=merchant-signing.pem
rm travelin-signing.pem merchant-signing.pem
```

## D. Akses untuk tim

Console → IAM & Admin → IAM → **Grant access**: masukkan email Randy, pilih role **Owner**. Randy harus menerima undangan yang masuk ke emailnya.

> Role Owner untuk akun Gmail tidak bisa diberikan lewat `gcloud`, jadi harus lewat console. Owner dibutuhkan untuk `gcloud run deploy --allow-unauthenticated`.

## E. Deploy rules dan smoke test

Di laptop yang ada repo `travelin`-nya:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project sosro-511617
npm i -g firebase-tools && firebase login
firebase use --add                      # pilih sosro-511617, alias: default
firebase deploy --only firestore,storage
```

Saat deploy pertama akan muncul permintaan izin agar Storage bisa membaca Firestore. Pilih **Yes**.

Lalu salin `api/.env.example` ke `api/.env`, isi `GOOGLE_CLOUD_PROJECT`, `STORAGE_BUCKET`, dan `PLACES_API_KEY`, kemudian jalankan:

```bash
uv run --project api python scripts/smoke_gemini.py
```

- Semua baris harus **PASS**.
- Kalau baris `planner model` gagal, ganti `PLANNER_MODEL=gemini-3.1-pro-preview` di `api/.env`, jalankan lagi, dan kabari hasilnya.
- Kalau sudah ada satu sample video, upload dengan `gcloud storage cp reel-1.mp4 gs://$BUCKET/samples/reels/`, lalu jalankan ulang dengan `--video gs://$BUCKET/samples/reels/reel-1.mp4`.

## F. Kirim ke Randy

Lewat chat pribadi, **jangan di-commit ke git**:

- Project ID dan nama bucket
- 6 nilai `firebaseConfig`, untuk `web/.env.local`
- Maps browser key dan Map ID
- Hasil smoke test

Places key tidak perlu dikirim karena sudah ada di Secret Manager. Untuk dipakai lokal, ambil dengan `gcloud secrets versions access latest --secret=places-api-key`.
