package com.poolar.controller.model;

public class Models {
    public static class TableState {
        public boolean detected;
        public Ball[] balls;
        public String mode;
    }
    public static class Ball {
        public float x, y;
        public float radius;
        public String color;
        public boolean isStripe, isSolid, isBlack, isCue;
    }
    public static class ScoreData {
        public int player1Score, player2Score;
        public int currentPlayer;
        public boolean gameOver;
        public int winner;
    }
    public static class TrainingLevel {
        public int level;
        public String name, description;
        public int drillCount;
    }
    public static class DrillInfo {
        public float[] cuePos, targetPos, pocketPos;
        public String description;
    }
    public static class DrillSession {
        public int level;
        public DrillInfo drill;
        public TrainingProgress progress;
    }
    public static class TrainingProgress {
        public int level, drill, totalDrills, consecutiveSuccesses, neededForPass;
        public String levelName;
    }
    public static class PlacementResult {
        public boolean cueCorrect, targetCorrect, allCorrect;
        public double cueError, targetError;
    }
    public static class TrainingResult {
        public boolean success, cueInZone, passed;
        public int consecutive;
        public String feedback;
    }
}
