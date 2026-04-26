package com.poolar.controller.network;

import com.google.gson.Gson;
import com.poolar.controller.model.Models;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;
import com.google.gson.reflect.TypeToken;

public class ApiClient {
    private final String baseUrl;
    private final Gson gson = new Gson();

    public ApiClient(String host) {
        this.baseUrl = "http://" + host + ":8000";
    }

    public interface ApiCallback<T> {
        void onResult(T result);
        void onError(String error);
    }

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

    public static class StatusResult {
        public String status, mode;
        public boolean camera, tableDetected;
        public int ballCount;
    }
}
