# Phase 0 Security Operations

The Streamlit application binds to `127.0.0.1` by default. Remote/mobile mode is an
explicit opt-in through `start_mobile_access.bat`, which binds Streamlit to all
interfaces and sets `FOREX_REMOTE_ACCESS=1`.

Remote mode requires `APP_ACCESS_TOKEN` in an untracked `.env` file or the service
environment. The application checks that token before it renders MT5 login or any
trading control. Do not place a real token in `.env.example`, source control, a URL,
or a command-line argument.

The mobile URL uses plain HTTP at the application layer. Its confidentiality depends
on the encrypted Tailscale connection; it must not be exposed directly to the public
internet. A reverse proxy with TLS is required for access outside that private path.

Dashboard MT5 passwords are held in Streamlit session memory. When the user opts to
remember a password, the application uses the operating system credential store via
`keyring`. If no secure keyring backend is available, persistence is disabled and the
password must be entered again. Session JSON contains preferences only.

Bot startup sends credentials through a child-only environment and verifies the
connected account identifier and, when MT5 reports it, the broker server. A mismatch
aborts startup before the trading loop begins.

Firebase mobile client configuration (`google-services.json` and
`firebase_options.dart`) is no longer tracked. These files normally contain public
project/client identifiers rather than a privileged service-account private key, but
removing them means Firebase-enabled Android and Flutter builds must regenerate or
provision the correct client configuration locally before building. Privileged
service-account JSON remains an ignored local credential under `secrets/`; Firebase
database and storage rules still require a separate owner review.
