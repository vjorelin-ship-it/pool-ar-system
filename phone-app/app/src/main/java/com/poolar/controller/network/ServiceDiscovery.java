package com.poolar.controller.network;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

public class ServiceDiscovery {
    private static final int DISCOVERY_PORT = 8001;
    private static final int TIMEOUT_MS = 3000;

    public interface DiscoveryCallback {
        void onFound(String host, int port);
        void onError(String message);
    }

    public void discoverServer(final DiscoveryCallback callback) {
        new Thread(() -> {
            try (DatagramSocket socket = new DatagramSocket()) {
                socket.setBroadcast(true);
                socket.setSoTimeout(TIMEOUT_MS);
                byte[] request = "POOL_AR_DISCOVER".getBytes();
                DatagramPacket packet = new DatagramPacket(
                    request, request.length,
                    InetAddress.getByName("255.255.255.255"), DISCOVERY_PORT);
                socket.send(packet);
                byte[] buffer = new byte[256];
                DatagramPacket response = new DatagramPacket(buffer, buffer.length);
                socket.receive(response);
                String reply = new String(response.getData(), 0, response.getLength());
                if (reply.startsWith("POOL_AR_SERVER:")) {
                    String[] parts = reply.split(":");
                    if (parts.length >= 2) {
                        callback.onFound(parts[1], 8000);
                        return;
                    }
                }
                callback.onError("Invalid response");
            } catch (java.net.SocketTimeoutException e) {
                callback.onError("未找到服务器，请确保电脑端已启动");
            } catch (Exception e) {
                callback.onError("发现服务失败: " + e.getMessage());
            }
        }).start();
    }
}
