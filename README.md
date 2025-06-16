# ZHA Device Status Dashboard

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io/)

A Home Assistant add-on providing a dedicated web interface to monitor the status of your Zigbee devices connected via ZHA. Get a quick overview of which devices are online, when they were last seen, their signal quality, battery levels, and track how many times they've gone offline.

---

## ✨ Features

* **Comprehensive Device List:** View all your ZHA devices in one place.
* **Key Metrics at a Glance:** Displays:
    * Device Name
    * Current Online/Offline Status
    * Last Seen Timestamp (when the device last communicated)
    * Home Assistant Area (if assigned)
    * Manufacturer and Model
    * Zigbee LQI (Link Quality Indicator)
    * Zigbee RSSI (Received Signal Strength Indicator)
    * IEEE Address
    * Battery Level (for battery-powered devices)
* **Offline Tracking:** A unique "Offline Count" feature that increments each time a device goes from an online to an offline state.
* **Configurable Offline Threshold:** Define how many minutes of inactivity marks a device as "Offline."
* **Interactive Table:** Features search, sortable columns, and pagination for easy navigation, powered by DataTables.
* **Simple Web UI:** Access the dashboard directly via the add-on's "Open Web UI" button.
* **API Endpoint:** Provides a `/api/stats` endpoint for programmatic access to aggregated device statistics.

---

## 🚀 Installation

This add-on is a custom Home Assistant add-on.

1.  **Add the Custom Repository:**
    * In Home Assistant, navigate to **Settings** -> **Add-ons**.
    * Click the **"Add-on Store"** tab.
    * Click the **three dots** in the top right corner (⋮) and select **"Repositories"**.
    * Add the URL for this add-on's repository: `[https://github.com/ianpleasance/home-assistant-zha-status]` (e.g., `https://github.com/ianpleasance/home-assistant-zha-status`)
    * Click "Add", then "Close".
2.  **Find and Install the Add-on:**
    * Back in the Add-on Store, click the **three dots** again and select **"Check for updates"** (or simply refresh the page).
    * You should now see "ZHA Device Status Dashboard" appear in the list.
    * Click on the add-on and then click **"INSTALL"**.

---

## 🔧 Configuration

Before starting the add-on, you must configure a few essential options.

1.  After installation, go to the **"Configuration"** tab of the "ZHA Device Status Dashboard" add-on page.

2.  You will see the following options:

    * **Home Assistant Long-Lived Access Token (`ha_token`)**
        * **Purpose:** This is essential for the add-on to communicate with your Home Assistant instance and retrieve ZHA device data.
        * **How to Generate:**
            1.  In your Home Assistant interface, click on your **user profile icon/name** in the bottom-left sidebar.
            2.  Scroll down to the **"Long-Lived Access Tokens"** section.
            3.  Click the **"CREATE TOKEN"** button.
            4.  Give the token a descriptive name (e.g., "ZHA Status Add-on Token").
            5.  **IMPORTANT:** A token will be displayed **only once**. Copy this token immediately and paste it into the `Home Assistant Long-Lived Access Token` field in the add-on configuration. If you lose it, you'll have to create a new one.

    * **Use SSL/TLS for HA Connection (`use_ssl`)**
        * **Type:** Toggle (boolean)
        * **Default:** `false`
        * **Purpose:** Enable this if your Home Assistant instance is accessed via HTTPS/SSL/TLS (which is highly recommended for security). This ensures the add-on connects securely using `wss://`. If disabled, it will attempt to connect via `ws://`.

    * **Enable Debug Logging (`debug`)**
        * **Type:** Toggle (boolean)
        * **Default:** `false`
        * **Purpose:** If enabled, the add-on will output more verbose messages to the add-on logs, including detailed API requests and responses. This is very useful for troubleshooting.

    * **Offline Threshold (minutes) (`offline_threshold_minutes`)**
        * **Type:** Integer
        * **Default:** `60`
        * **Purpose:** This defines the number of minutes of inactivity (no `last_seen` update) after which a ZHA device is considered 'Offline' by the dashboard. This also triggers an increment of the device's "Offline Count" if it was previously online.

3.  After entering your token and adjusting other settings, click **"SAVE"**.

---

## 🚀 How to Use

1.  **Start the Add-on:** After saving your configuration, navigate to the **"Info"** tab of the add-on page and click **"START"**.
2.  **Monitor Logs (Optional but Recommended):** Keep an eye on the **"Logs"** tab to ensure the add-on starts without errors and is successfully connecting to Home Assistant.
3.  **Open the Web Interface:** Once the add-on is running, click **"OPEN WEB UI"** on the "Info" tab.
4.  **Refresh Data:** The data is collected when the add-on starts and when you click the **"🔁 Refresh Now"** button on the dashboard. Click this button to get the latest status of your devices.
5.  **Utilize Table Features:**
    * Use the **search box** to quickly find devices by name, model, area, etc.
    * Click on **column headers** to sort the table by that column (e.g., sort by "Last Seen" to see oldest activity, or "Offline Count" to see problematic devices).
    * Use the **pagination controls** and the "Show X entries" dropdown (including "All") to manage the number of devices displayed.

---

## 🏠 Adding to Home Assistant Dashboard (Lovelace)

You can embed the ZHA Device Status Dashboard directly into your Home Assistant Lovelace dashboard for quick access.

1.  Go to your Home Assistant Dashboard where you want to add the card.
2.  Click the **three dots** in the top right corner (⋮) -> **"Edit Dashboard"**.
3.  Click **"Add Card"** (the blue plus button).
4.  Search for and select the **"Iframe"** card.
5.  In the configuration, set the `url` to your add-on's web interface. This is typically `http://<YOUR_HOME_ASSISTANT_IP_ADDRESS>:5000` (replace `<YOUR_HOME_ASSISTANT_IP_ADDRESS>` with the actual IP address or hostname of your Home Assistant instance, and adjust the port if you've changed it in the add-on's network configuration).
6.  Adjust `aspect_ratio` or `height` as needed for proper display.

    **Example YAML for the Iframe Card:**

    ```yaml
    type: iframe
    url: [http://homeassistant.local:5000](http://homeassistant.local:5000)
    title: ZHA Device Status
    aspect_ratio: 70% # Or set a fixed height: height: 600
    ```

### **🚨 Important Caveat: Mixed Content (SSL/HTTPS)**

**If your Home Assistant instance itself is served via HTTPS (SSL/TLS), you CANNOT embed an `http://` iframe.** Modern web browsers block "mixed content" (loading insecure `http://` content within a secure `https://` page) as a security measure.

* If your Home Assistant URL starts with `https://`, and your add-on's URL starts with `http://`, the iframe will be blocked and won't show the dashboard.
* To embed it, both the parent page (Home Assistant) and the iframe content (your add-on) **must** use the same protocol (i.e., both `https://`).
* Currently, this add-on does not support serving its web page via HTTPS directly from within the add-on itself. Therefore, if your Home Assistant is on HTTPS, you will need to access the add-on's web UI by going directly to its `http://<IP>:5000` address in a new browser tab.
