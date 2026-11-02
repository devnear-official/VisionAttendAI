#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include "network_config.h"

class WiFiConfigManager {
private:
    Preferences m_prefs;
    WebServer m_server;
    DNSServer m_dnsServer;
    String m_ssid;
    String m_password;
    String m_backendHost;
    uint16_t m_backendPort;
    bool m_inPortalMode = false;

public:
    WiFiConfigManager() : m_server(80), m_backendPort(8000) {}

    const String& getSSID() const { return m_ssid; }
    const String& getBackendHost() const { return m_backendHost; }
    uint16_t getBackendPort() const { return m_backendPort; }

    void loadConfig() {
        m_prefs.begin("va_wifi", false);
        m_ssid = m_prefs.getString("ssid", WIFI_SSID);
        m_password = m_prefs.getString("pass", WIFI_PASSWORD);
        m_backendHost = m_prefs.getString("host", BACKEND_HOST);
        m_backendPort = m_prefs.getUShort("port", BACKEND_PORT);
        m_prefs.end();

        Serial.printf("[WiFiManager] Loaded Config: SSID='%s', Host='%s', Port=%d\n",
                      m_ssid.c_str(), m_backendHost.c_str(), m_backendPort);
    }

    void saveConfig(const String& ssid, const String& pass, const String& host, uint16_t port) {
        m_prefs.begin("va_wifi", false);
        m_prefs.putString("ssid", ssid);
        m_prefs.putString("pass", pass);
        m_prefs.putString("host", host);
        m_prefs.putUShort("port", port);
        m_prefs.end();

        m_ssid = ssid;
        m_password = pass;
        m_backendHost = host;
        m_backendPort = port;

        Serial.printf("[WiFiManager] Saved Config: SSID='%s', Host='%s', Port=%d\n",
                      m_ssid.c_str(), m_backendHost.c_str(), m_backendPort);
    }

    bool connectStation(unsigned long timeoutMs = 8000) {
        if (m_ssid.length() == 0) return false;

        Serial.printf("[WiFi] Attempting to connect to '%s'...\n", m_ssid.c_str());
        WiFi.mode(WIFI_STA);
        WiFi.begin(m_ssid.c_str(), m_password.c_str());

        unsigned long start = millis();
        while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
            delay(200);
            Serial.print(".");
        }
        Serial.println();

        if (WiFi.status() == WL_CONNECTED) {
            Serial.printf("[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
            return true;
        }
        return false;
    }

    void startPortal(Adafruit_ILI9341* tft = nullptr) {
        m_inPortalMode = true;
        WiFi.disconnect(true);
        delay(100);

        IPAddress apIP(192, 168, 4, 1);
        IPAddress netMsk(255, 255, 255, 0);

        WiFi.mode(WIFI_AP);
        WiFi.softAPConfig(apIP, apIP, netMsk);
        WiFi.softAP("Setup");

        m_dnsServer.setErrorReplyCode(DNSReplyCode::NoError);
        m_dnsServer.start(53, "*", apIP);

        Serial.println("\n========================================");
        Serial.println("[WiFi Portal] Started Access Point 'Setup'");
        Serial.println("[WiFi Portal] Connect phone/PC to 'Setup'");
        Serial.println("[WiFi Portal] Browse to: http://192.168.4.1");
        Serial.println("========================================\n");

        if (tft != nullptr) {
            tft->fillScreen(ILI9341_BLACK);
            tft->setCursor(8, 20);
            tft->setTextColor(ILI9341_YELLOW);
            tft->setTextSize(2);
            tft->println("WiFi Setup Required");

            tft->setTextColor(ILI9341_WHITE);
            tft->setTextSize(1);
            tft->setCursor(8, 60);
            tft->println("Could not connect to saved WiFi.");
            tft->println("Broadcasting hotspot:");

            tft->setCursor(8, 95);
            tft->setTextColor(ILI9341_CYAN);
            tft->setTextSize(2);
            tft->println("WiFi: Setup");

            tft->setCursor(8, 130);
            tft->setTextColor(ILI9341_GREEN);
            tft->setTextSize(2);
            tft->println("IP: 192.168.4.1");

            tft->setCursor(8, 175);
            tft->setTextColor(ILI9341_LIGHTGREY);
            tft->setTextSize(1);
            tft->println("1. Connect mobile to WiFi 'Setup'");
            tft->println("2. Open browser: http://192.168.4.1");
            tft->println("3. Select your router/hotspot & enter");
            tft->println("   your laptop's backend IP.");
        }

        setupWebHandlers();
        m_server.begin();

        while (m_inPortalMode) {
            m_dnsServer.processNextRequest();
            m_server.handleClient();
            delay(10);
        }
    }

private:
    void setupWebHandlers() {
        m_server.on("/", HTTP_GET, [this]() {
            handleRoot();
        });

        m_server.on("/save", HTTP_POST, [this]() {
            handleSave();
        });

        // Captive portal detection endpoints
        m_server.on("/generate_204", HTTP_GET, [this]() { handleRoot(); });
        m_server.on("/hotspot-detect.html", HTTP_GET, [this]() { handleRoot(); });
        m_server.on("/ncsi.txt", HTTP_GET, [this]() { handleRoot(); });

        m_server.onNotFound([this]() {
            m_server.sendHeader("Location", "http://192.168.4.1/", true);
            m_server.send(302, "text/plain", "");
        });
    }

    void handleRoot() {
        Serial.println("[Web] Scanning nearby Wi-Fi networks...");
        int n = WiFi.scanNetworks();

        String html = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>";
        html += "<title>VisionAttend-AI Setup</title>";
        html += "<style>";
        html += "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }";
        html += ".card { max-width: 440px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); border: 1px solid #334155; }";
        html += "h2 { margin-top: 0; color: #38bdf8; font-size: 22px; text-align: center; }";
        html += "p { color: #94a3b8; font-size: 14px; text-align: center; }";
        html += "label { display: block; margin-top: 14px; font-weight: 600; font-size: 13px; color: #cbd5e1; }";
        html += "input, select { width: 100%; box-sizing: border-box; padding: 10px 12px; margin-top: 6px; background: #0f172a; border: 1px solid #475569; border-radius: 8px; color: #fff; font-size: 15px; }";
        html += "input:focus, select:focus { border-color: #38bdf8; outline: none; }";
        html += "button { width: 100%; margin-top: 22px; padding: 12px; background: #2563eb; color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }";
        html += "button:hover { background: #1d4ed8; }";
        html += ".hint { font-size: 11px; color: #64748b; margin-top: 4px; }";
        html += "</style></head><body><div class='card'>";
        html += "<h2>VisionAttend-AI</h2>";
        html += "<p>Configure Wi-Fi & Laptop Backend Server</p>";
        html += "<form action='/save' method='POST'>";

        // SSID selector
        html += "<label for='ssid'>Wi-Fi Network (SSID):</label>";
        html += "<select name='ssid' id='ssid' onchange='checkCustom(this.value)'>";
        if (n > 0) {
            for (int i = 0; i < n; ++i) {
                String scannedSsid = WiFi.SSID(i);
                int rssi = WiFi.RSSI(i);
                html += "<option value='" + scannedSsid + "'";
                if (scannedSsid == m_ssid) html += " selected";
                html += ">" + scannedSsid + " (" + String(rssi) + " dBm)</option>";
            }
        }
        html += "<option value='__custom__'>-- Enter Other SSID --</option>";
        html += "</select>";
        html += "<input type='text' id='custom_ssid' name='custom_ssid' placeholder='Enter SSID manually' style='display:none; margin-top:8px;'>";

        // Password
        html += "<label for='pass'>Wi-Fi Password:</label>";
        html += "<input type='password' id='pass' name='pass' placeholder='Enter Wi-Fi password' value='" + m_password + "'>";

        // Backend Host IP
        html += "<label for='host'>Laptop Backend Server IP:</label>";
        html += "<input type='text' id='host' name='host' value='" + m_backendHost + "' placeholder='e.g. 192.168.43.100'>";
        html += "<div class='hint'>IP of the laptop running FastAPI (Check with 'ipconfig' in cmd).</div>";

        // Backend Port
        html += "<label for='port'>Backend Port:</label>";
        html += "<input type='number' id='port' name='port' value='" + String(m_backendPort) + "'>";

        html += "<button type='submit'>Save & Connect</button>";
        html += "</form>";
        html += "</div>";

        html += "<script>";
        html += "function checkCustom(val) {";
        html += "  var customInput = document.getElementById('custom_ssid');";
        html += "  if (val === '__custom__') { customInput.style.display = 'block'; customInput.required = true; }";
        html += "  else { customInput.style.display = 'none'; customInput.required = false; }";
        html += "}";
        html += "</script></body></html>";

        m_server.send(200, "text/html", html);
    }

    void handleSave() {
        String reqSsid = m_server.arg("ssid");
        String customSsid = m_server.arg("custom_ssid");
        if (reqSsid == "__custom__" && customSsid.length() > 0) {
            reqSsid = customSsid;
        }

        String reqPass = m_server.arg("pass");
        String reqHost = m_server.arg("host");
        String reqPortStr = m_server.arg("port");
        uint16_t reqPort = (reqPortStr.length() > 0) ? (uint16_t)reqPortStr.toInt() : 8000;

        saveConfig(reqSsid, reqPass, reqHost, reqPort);

        String html = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>";
        html += "<style>body{font-family:sans-serif;background:#0f172a;color:#fff;text-align:center;padding:40px;}</style></head>";
        html += "<body><h2>Settings Saved!</h2>";
        html += "<p>ESP32 is now restarting and connecting to <b>" + reqSsid + "</b>...</p>";
        html += "<p>Backend Host set to: <b>" + reqHost + ":" + String(reqPort) + "</b></p>";
        html += "<p>You may now connect your phone/laptop back to " + reqSsid + ".</p>";
        html += "</body></html>";

        m_server.send(200, "text/html", html);

        delay(1500);
        m_inPortalMode = false;
        ESP.restart();
    }
};

extern WiFiConfigManager wifiConfigManager;
