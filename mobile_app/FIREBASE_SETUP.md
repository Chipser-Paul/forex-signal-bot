# Android Push Setup (FCM)

## 1) Firebase project
1. Create a Firebase project.
2. Add an Android app with package name from `mobile_app/android/app/build.gradle.kts`:
   - `applicationId = "com.example.mobile_app"`
3. Download `google-services.json`.
4. Put it here:
   - `mobile_app/android/app/google-services.json`
5. This file is used to generate `mobile_app/lib/firebase_options.dart` for manual init.

## 2) Build and install app
1. In `mobile_app` run:
   - `C:\flutter\bin\flutter pub get`
   - `C:\flutter\bin\flutter run`
2. Open app settings in the app.
3. In **Push Notifications (FCM)**, press **Refresh Token**.
4. Copy token with **Copy Token**.

## 3) Backend service account
1. In Firebase Console -> Project settings -> Service accounts.
2. Generate a new private key JSON.
3. Save file at:
   - `secrets/firebase-service-account.json`

## 4) Configure backend `.env`
Set:

```env
FIREBASE_SERVICE_ACCOUNT_PATH=secrets/firebase-service-account.json
FCM_DEVICE_TOKEN=<paste-token-from-mobile-app>
```

For multiple phones, use:

```env
FCM_DEVICE_TOKENS=token1,token2,token3
```

## 5) Install backend dependency
From repo root:

```powershell
pip install -r requirements.txt
```

## 6) Restart bot + frontend
Restart bot process and Streamlit frontend so new env/settings load.

## 7) Expected events
- Trade placed
- Trade exited
- Daily target reached
