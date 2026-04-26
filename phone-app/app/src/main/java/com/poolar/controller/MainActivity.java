package com.poolar.controller;

import android.os.Bundle;
import android.widget.FrameLayout;
import androidx.appcompat.app.AppCompatActivity;
import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentManager;
import androidx.fragment.app.FragmentTransaction;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.poolar.controller.ui.HomeFragment;
import com.poolar.controller.ui.ActiveFragment;
import com.poolar.controller.ui.SettingsFragment;

public class MainActivity extends AppCompatActivity {

    private BottomNavigationView bottomNav;
    private String currentMode = "idle"; // idle, match, training, challenge
    private String player1Name = "选手一";
    private String player2Name = "选手二";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        bottomNav = findViewById(R.id.bottom_nav);

        if (savedInstanceState == null) {
            switchFragment(new HomeFragment(), "home");
        }

        bottomNav.setOnItemSelectedListener(item -> {
            Fragment f = null;
            String tag = "";
            int id = item.getItemId();
            if (id == R.id.nav_home) {
                f = new HomeFragment();
                tag = "home";
            } else if (id == R.id.nav_active) {
                f = new ActiveFragment();
                tag = "active";
            } else if (id == R.id.nav_settings) {
                f = new SettingsFragment();
                tag = "settings";
            }
            if (f != null) {
                switchFragment(f, tag);
            }
            return true;
        });
    }

    private void switchFragment(Fragment fragment, String tag) {
        FragmentManager fm = getSupportFragmentManager();
        FragmentTransaction tx = fm.beginTransaction();
        tx.replace(R.id.fragment_container, fragment, tag);
        tx.commit();
    }

    public void switchTab(int tabId) {
        bottomNav.setSelectedItemId(tabId);
    }

    public void setCurrentMode(String mode) {
        this.currentMode = mode;
    }

    public String getCurrentMode() {
        return currentMode;
    }

    public void setPlayerNames(String p1, String p2) {
        this.player1Name = p1;
        this.player2Name = p2;
    }

    public String getPlayer1Name() { return player1Name; }
    public String getPlayer2Name() { return player2Name; }
}
