package com.poolar.controller.network;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import java.net.URI;
import java.util.concurrent.CopyOnWriteArrayList;

public class WebSocketClient {
    private static final String TAG = "PoolAR-WS";
    private final Gson gson = new Gson();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final CopyOnWriteArrayList<MessageListener> listeners = new CopyOnWriteArrayList<>();
    private org.java_websocket.client.WebSocketClient ws;
    private String host;
    private int port;
    private String path;
    private boolean shouldReconnect = true;

    public interface MessageListener {
        void onMessage(String type, JsonObject data);
        default void onConnected() {}
        default void onDisconnected() {}
    }

    public WebSocketClient() {}

    public void connect(String host, int port, String path) {
        this.host = host;
        this.port = port;
        this.path = path;
        this.shouldReconnect = true;
        doConnect();
    }

    private void doConnect() {
        String url = "ws://" + host + ":" + port + path;
        try {
            ws = new org.java_websocket.client.WebSocketClient(new URI(url)) {
                @Override
                public void onOpen(org.java_websocket.handshake.ServerHandshake handshake) {
                    Log.d(TAG, "Connected to " + url);
                    mainHandler.post(() -> {
                        for (MessageListener l : listeners) l.onConnected();
                    });
                }

                @Override
                public void onMessage(String message) {
                    try {
                        JsonObject json = gson.fromJson(message, JsonObject.class);
                        String type = json.has("type") ? json.get("type").getAsString() : "";
                        JsonObject data = json.has("data") ? json.getAsJsonObject("data") : new JsonObject();
                        mainHandler.post(() -> {
                            for (MessageListener l : listeners) l.onMessage(type, data);
                        });
                    } catch (Exception e) {
                        Log.e(TAG, "Parse error", e);
                    }
                }

                @Override
                public void onClose(int code, String reason, boolean remote) {
                    Log.d(TAG, "Disconnected: " + reason);
                    mainHandler.post(() -> {
                        for (MessageListener l : listeners) l.onDisconnected();
                    });
                    if (shouldReconnect) {
                        mainHandler.postDelayed(() -> doConnect(), 3000);
                    }
                }

                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "WS error", ex);
                }
            };
            ws.connect();
        } catch (Exception e) {
            Log.e(TAG, "Connect failed", e);
            if (shouldReconnect) {
                mainHandler.postDelayed(() -> doConnect(), 3000);
            }
        }
    }

    public void addListener(MessageListener listener) {
        listeners.add(listener);
    }

    public void removeListener(MessageListener listener) {
        listeners.remove(listener);
    }

    public void send(JsonObject msg) {
        if (ws != null && ws.isOpen()) {
            try {
                ws.send(gson.toJson(msg));
            } catch (Exception e) {
                Log.e(TAG, "Send error", e);
            }
        }
    }

    public void disconnect() {
        shouldReconnect = false;
        if (ws != null) {
            try { ws.close(); } catch (Exception e) {}
        }
    }

    public boolean isConnected() {
        return ws != null && ws.isOpen();
    }
}
