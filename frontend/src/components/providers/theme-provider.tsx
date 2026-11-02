"use client";

import React, { createContext, useContext, useCallback, useSyncExternalStore } from "react";

type Theme = "light" | "dark";

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: "light",
  toggleTheme: () => {},
  setTheme: () => {},
});

function getThemeSnapshot(): Theme {
  if (typeof window === "undefined") return "light";
  return localStorage.getItem("va_theme") === "dark" ? "dark" : "light";
}

function getServerSnapshot(): Theme {
  return "light"; // Default to light theme
}

function subscribeToTheme(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("va_theme_change", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("va_theme_change", callback);
  };
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(subscribeToTheme, getThemeSnapshot, getServerSnapshot);

  const setTheme = useCallback((newTheme: Theme) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("va_theme", newTheme);
      if (newTheme === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
      window.dispatchEvent(new Event("va_theme_change"));
    }
  }, []);

  const toggleTheme = useCallback(() => {
    const current = getThemeSnapshot();
    const next: Theme = current === "light" ? "dark" : "light";
    setTheme(next);
  }, [setTheme]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      <script
        dangerouslySetInnerHTML={{
          __html: `
            (function() {
              try {
                var saved = localStorage.getItem('va_theme');
                if (saved === 'dark') {
                  document.documentElement.classList.add('dark');
                } else {
                  document.documentElement.classList.remove('dark');
                }
              } catch(e) {}
            })();
          `,
        }}
      />
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
