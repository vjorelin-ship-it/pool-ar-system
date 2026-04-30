package com.poolar.controller.network;

import com.google.gson.FieldNamingPolicy;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.poolar.controller.model.Models;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;
import com.google.gson.reflect.TypeToken;
import org.json.JSONObject;

public class ApiClient {
    private final String baseUrl;
    private final Gson gson;

    // ── Callback interfaces ──────────────────────────

    public interface ApiCallback<T> {
        void onResult(T result);
        void onError(String error);
    }

    @FunctionalInterface
    public interface SuccessCallback {
        void onResult(boolean success);
    }

    @FunctionalInterface
    public interface DataCallback {
        void onResult(JSONObject data);
    }

    // ── Static singleton ─────────────────────────────

    private static ApiClient instance;

    public static void init(String host) {
        instance = new ApiClient(host);
    }

    public static ApiClient getInstance() {
        return instance;
    }

    // ── Static convenience methods ───────────────────

    public static void setMode(String mode, SuccessCallback callback) {
        if (instance == null) { callback.onResult(false); return; }
        instance.setMode(mode, new ApiCallback<Object>() {
            @Override public void onResult(Object result) { callback.onResult(true); }
            @Override public void onError(String error) { callback.onResult(false); }
        });
    }

    public static void control(String action, SuccessCallback callback) {
        if (instance == null) { callback.onResult(false); return; }
        ApiCallback<Void> cb = new ApiCallback<Void>() {
            @Override public void onResult(Void result) { callback.onResult(true); }
            @Override public void onError(String error) { callback.onResult(false); }
        };
        if ("start".equals(action)) instance.startSystem(cb);
        else if ("stop".equals(action)) instance.stopSystem(cb);
        else callback.onResult(false);
    }

    public static void getStatus(DataCallback callback) {
        if (instance == null) { callback.onResult(null); return; }
        instance.getStatus(new ApiCallback<StatusResult>() {
            @Override public void onResult(StatusResult result) {
                try {
                    JSONObject json = new JSONObject();
                    json.put("status", result.status != null ? result.status : "");
                    json.put("mode", result.mode != null ? result.mode : "idle");
                    json.put("ball_count", result.ballCount);
                    callback.onResult(json);
                } catch (Exception e) { callback.onResult(null); }
            }
            @Override public void onError(String error) { callback.onResult(null); }
        });
    }

    public static void getScore(DataCallback callback) {
        if (instance == null) { callback.onResult(null); return; }
        instance.getScore(new ApiCallback<Models.ScoreData>() {
            @Override public void onResult(Models.ScoreData result) {
                try {
                    JSONObject json = new JSONObject();
                    json.put("player1_score", result.player1Score);
                    json.put("player2_score", result.player2Score);
                    callback.onResult(json);
                } catch (Exception e) { callback.onResult(null); }
            }
            @Override public void onError(String error) { callback.onResult(null); }
        });
    }

    public static void get(String path, DataCallback callback) {
        if (instance == null) { callback.onResult(null); return; }
        instance.getJson(path, callback);
    }

    public static void post(String path, JSONObject body, SuccessCallback callback) {
        if (instance == null) { callback.onResult(false); return; }
        instance.postJson(path, body, callback);
    }

    // ── Constructor ──────────────────────────────────

    public ApiClient(String host) {
        this.baseUrl = "http://" + host + ":8000";
        this.gson = new GsonBuilder()
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
            .create();
    }

    // ── Typed instance methods ───────────────────────

    public void getStatus(final ApiCallback<StatusResult> callback) {
        get("/api/status", StatusResult.class, callback);
    }
    public void startSystem(final ApiCallback<Void> callback) {
        post("/api/control/start", null, Void.class, callback);
    }
    public void stopSystem(final ApiCallback<Void> callback) {
        post("/api/control/stop", null, Void.class, callback);
    }
    public void setMode(String mode, final ApiCallback<Object> callback) {
        post("/api/mode?mode=" + mode, null, Object.class, callback);
    }
    public void getScore(final ApiCallback<Models.ScoreData> callback) {
        get("/api/score", Models.ScoreData.class, callback);
    }
    public void getTrainingLevels(final ApiCallback<List<Models.TrainingLevel>> callback) {
        getList("/api/training/levels", Models.TrainingLevel.class, callback);
    }
    public void selectLevel(int level, final ApiCallback<Models.DrillSession> callback) {
        post("/api/training/select-level?level=" + level, null, Models.DrillSession.class, callback);
    }
    public void startCalibration(final ApiCallback<Void> callback) {
        post("/api/calibration/start", null, Void.class, callback);
    }
    public void stopCalibration(final ApiCallback<Void> callback) {
        post("/api/calibration/stop", null, Void.class, callback);
    }
    public void getCalibrationStatus(final ApiCallback<CalibrationStatusResult> callback) {
        get("/api/calibration/status", CalibrationStatusResult.class, callback);
    }

    // ── Raw JSON instance methods ────────────────────

    public void getJson(String path, DataCallback callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
                reader.close();
                callback.onResult(new JSONObject(response.toString()));
            } catch (Exception e) { callback.onResult(null); }
        }).start();
    }

    public void postJson(String path, JSONObject body, SuccessCallback callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                if (body != null) {
                    OutputStream os = conn.getOutputStream();
                    os.write(body.toString().getBytes());
                    os.flush();
                }
                int code = conn.getResponseCode();
                callback.onResult(code >= 200 && code < 300);
            } catch (Exception e) { callback.onResult(false); }
        }).start();
    }

    // ── Private HTTP helpers ─────────────────────────

    private <T> void get(String path, Class<T> clazz, ApiCallback<T> callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
                reader.close();
                callback.onResult(gson.fromJson(response.toString(), clazz));
            } catch (Exception e) { callback.onError(e.getMessage()); }
        }).start();
    }

    private <T> void getList(String path, Class<T> clazz, ApiCallback<List<T>> callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
                reader.close();
                callback.onResult(gson.fromJson(response.toString(),
                    TypeToken.getParameterized(List.class, clazz).getType()));
            } catch (Exception e) { callback.onError(e.getMessage()); }
        }).start();
    }

    private <T> void post(String path, Object body, Class<T> clazz, ApiCallback<T> callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                if (body != null) {
                    OutputStream os = conn.getOutputStream();
                    os.write(gson.toJson(body).getBytes());
                    os.flush();
                }
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
                reader.close();
                T result = gson.fromJson(response.toString(), clazz);
                callback.onResult(result);
            } catch (Exception e) { callback.onError(e.getMessage()); }
        }).start();
    }

    // ── Data classes ─────────────────────────────────

    public static class StatusResult {
        public String status, mode;
        public boolean camera, tableDetected;
        public int ballCount;
    }

    public static class CalibrationStatusResult {
        public boolean active;
        public boolean tableDetected;
        public String status;
        public String[][] markers;
    }
}
