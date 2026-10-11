# OTM · Order Flow — shell pubblica

Contiene solo la shell Streamlit. Le viste (Footprint, FakeMove E/L/C) NON sono qui:
l'app le scarica all'avvio dal repo privato `JER55/otm-streamlit` (cartella `views/`)
usando il token nei Secrets di Streamlit Cloud:

```
APP_PASSWORD = "..."
GITHUB_TOKEN = "github_pat_..."
```
