# FusionSolar Charger – Home Assistant Integration

## 📌 Overview

**FusionSolar Charger** is a custom integration for Home Assistant that connects to Huawei FusionSolar systems and exposes charger-related data and controls within your smart home environment.

This integration allows you to monitor and manage your FusionSolar charger directly from Home Assistant, enabling automation, insights, and better energy management.

---

## ✨ Features

* 🔌 Monitor charger status
* ⚡ View real-time power and energy data
* 📊 Integration with Home Assistant Energy Dashboard
* 🔄 Automatic data updates via coordinator pattern
* ⚙️ Config Flow support (UI-based setup)
* 🌍 Cloud-based connection to FusionSolar

---

## 📦 Installation

### Option 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Click the three dots (top right) → **Custom repositories**
4. Add this repository URL
5. Select category: **Integration**
6. Install **FusionSolar Charger**
7. Restart Home Assistant

---

### Option 2: Manual Installation

1. Download this repository

2. Copy the folder:

   ```
   custom_components/fusionsolar_charger/
   ```

   into your Home Assistant `custom_components` directory

3. Restart Home Assistant

---

## ⚙️ Configuration

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **FusionSolar Charger**
4. Enter your FusionSolar credentials

---

## 🔐 Requirements

* A valid Huawei FusionSolar account
* Internet access (cloud-based API)

---

## 🧠 How It Works

This integration connects to the FusionSolar cloud API and retrieves charger data at regular intervals. It uses Home Assistant’s DataUpdateCoordinator to efficiently manage updates and minimize API load.

---

## ⚠️ Known Limitations

* Depends on FusionSolar cloud availability
* API rate limits may apply
* Not officially supported by Huawei

---

## 🛠️ Troubleshooting

### Integration not showing up

* Ensure files are in the correct directory:

  ```
  custom_components/fusionsolar_charger/
  ```
* Restart Home Assistant

### Login issues

* Double-check credentials
* Verify your FusionSolar account works via official app/portal

---

## 🧑‍💻 Development

### Structure

```
custom_components/fusionsolar_charger/
├── __init__.py
├── manifest.json
├── config_flow.py
├── coordinator.py
├── api.py
├── sensor.py
└── translations/
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to:

* Open issues
* Submit pull requests
* Suggest improvements

---

## 📄 License

MIT License (or update this to your actual license)

---

## ⚠️ Disclaimer

This project is not affiliated with or endorsed by Huawei or FusionSolar. Use at your own risk.

---

## ⭐ Support

If you find this project useful, consider giving it a star ⭐ on GitHub!
