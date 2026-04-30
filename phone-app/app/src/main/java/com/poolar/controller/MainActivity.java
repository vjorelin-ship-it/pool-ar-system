package com.poolar.controller;

import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;
import androidx.fragment.app.Fragment;
import com.google.android.material.bottomnavigation.BottomNavigationView;

public class MainActivity extends AppCompatActivity {
    private static final String TAG = "PoolARController";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        BottomNavigationView nav = findViewById(R.id.bottomNav);
        nav.setOnItemSelectedListener(item -> {
            Fragment frag;
            int id = item.getItemId();
            if (id == R.id.nav_home) {
                frag = new HomeFragment();
            } else if (id == R.id.nav_progress) {
                frag = new InProgressFragment();
            } else if (id == R.id.nav_settings) {
                frag = new SettingsFragment();
            } else {
                return false;
            }
            getSupportFragmentManager().beginTransaction()
                .replace(R.id.fragmentContainer, frag).commit();
            return true;
        });
        // Load default tab
        nav.setSelectedItemId(R.id.nav_home);
    }
}
