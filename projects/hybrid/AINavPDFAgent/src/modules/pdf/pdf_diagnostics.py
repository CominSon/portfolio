# modules/pdf_diagnostics.py
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver


DEFAULT_SCROLL_CANDIDATES = [
    "div.ScreenLayout.autoscroll-y",
    "div.Dashboard.grow-1.flex-col.autoscroll-y",
    "div.autoscroll-y",
    "div[style*='overflow-y:auto']",
    "div[style*='overflow: auto']",
]


class EnvDiagnostics:
    """
    Снимок окружения (монитор/браузер/страница/шапки/контейнер прокрутки)
    и сравнение двух снимков.
    """

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)

    # ===================== ПУБЛИЧНЫЕ МЕТОДЫ =====================

    def collect_env_snapshot(
        self,
        browser: WebDriver,
        logger,
        scroll_selectors: Optional[List[str]] = None,
        label: str = "snapshot",
    ) -> Dict[str, Any]:
        """
        Снять «снимок окружения», сохранить JSON, вернуть словарь.
        """
        if scroll_selectors is None:
            scroll_selectors = DEFAULT_SCROLL_CANDIDATES

        js_env = self._js_env_metrics(browser)
        sc_info = self._detect_scroll_container(browser, scroll_selectors)
        headers = self._measure_headers(browser)
        tiny_png_path, bmp_w, bmp_h = self._take_tiny_screenshot(browser, prefix=label)

        # k-факторы (отношение bitmap px к css px по вертикали)
        viewport_css_h = _dig(js_env, "window", "innerHeight")
        k_from_window = (bmp_h / viewport_css_h) if (bmp_h and viewport_css_h) else None

        sc_client_h = sc_info.get("clientHeight")
        k_from_scroll = (bmp_h / sc_client_h) if (bmp_h and sc_client_h) else None

        snap = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "label": label,
            "navigator": {
                "userAgent": _dig(js_env, "navigator", "userAgent"),
                "platform": _dig(js_env, "navigator", "platform"),
                "hardwareConcurrency": _dig(js_env, "navigator", "hardwareConcurrency"),
            },
            "screen": _dig(js_env, "screen") or {},
            "window": _dig(js_env, "window") or {},
            "visualViewport": _dig(js_env, "visualViewport") or {},
            "documentElement": _dig(js_env, "documentElement") or {},
            "selectedScrollContainer": sc_info,
            "headers": headers,
            "bitmapScreenshot": {
                "tiny_png_path": tiny_png_path,
                "bitmap_width": bmp_w,
                "bitmap_height": bmp_h,
            },
            "k_factors": {
                "k_from_window_inner": k_from_window,
                "k_from_scroll_client": k_from_scroll,
            },
        }

        out_path = os.path.join(self.temp_dir, f"{label}_{int(time.time())}.json")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=2)
            _log(logger, f"[DIAG] snapshot saved: {out_path}")
        except Exception as e:
            _log(logger, f"[DIAG] cannot save snapshot: {e}", level="error")

        self._log_brief(snap, logger)
        return snap

    @staticmethod
    def compare_snapshots(
        path_a: str,
        path_b: str,
        logger=None,
        keys_to_compare: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Сравнить два JSON-снимка и вернуть дельты по ключам.
        """
        def _load(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)

        a = _load(path_a)
        b = _load(path_b)

        if not keys_to_compare:
            keys_to_compare = [
                "devicePixelRatio",
                ("visualViewport", "scale"),
                ("screen", "width"),
                ("screen", "height"),
                ("window", "outerWidth"),
                ("window", "outerHeight"),
                ("window", "innerWidth"),
                ("window", "innerHeight"),
                ("documentElement", "clientWidth"),
                ("documentElement", "clientHeight"),
                ("selectedScrollContainer", "matched_selector"),
                ("selectedScrollContainer", "clientHeight"),
                ("selectedScrollContainer", "scrollHeight"),
                ("headers", "header_app_nav"),
                ("headers", "header_dashboard"),
                ("headers", "header_total"),
                ("k_factors", "k_from_window_inner"),
                ("k_factors", "k_from_scroll_client"),
            ]

        def _get(d, path):
            if isinstance(path, str):
                # плоские ключи для удобства: "devicePixelRatio" из window
                # попробуем искать и в window
                if path in d:
                    return d.get(path)
                return d.get("window", {}).get(path)
            cur = d
            for k in path:
                if not isinstance(cur, dict) or k not in cur:
                    return None
                cur = cur[k]
            return cur

        deltas = {}
        for key in keys_to_compare:
            av = _get(a, key)
            bv = _get(b, key)
            deltas[str(key)] = {"A": av, "B": bv, "Δ": _delta(av, bv)}

        if logger:
            logger.info("[DIAG] Snapshot diff:")
            for k, v in deltas.items():
                logger.info(f"  {k}: A={v['A']} | B={v['B']} | Δ={v['Δ']}")
        else:
            print("[DIAG] Snapshot diff:")
            for k, v in deltas.items():
                print(f"  {k}: A={v['A']} | B={v['B']} | Δ={v['Δ']}")

        return deltas

    # ===================== ВНУТРЕННИЕ УТИЛИТЫ =====================

    def _safe_js(self, browser: WebDriver, script: str):
        try:
            return browser.execute_script(script)
        except Exception:
            return None

    def _js_env_metrics(self, browser: WebDriver) -> Dict[str, Any]:
        js = """
        (() => {
          try {
            const vv = window.visualViewport || {};
            const docEl = document.documentElement || {};
            return {
              navigator: {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                hardwareConcurrency: navigator.hardwareConcurrency || null
              },
              screen: {
                width:  (screen && screen.width)  || null,
                height: (screen && screen.height) || null,
                availWidth:  (screen && screen.availWidth)  || null,
                availHeight: (screen && screen.availHeight) || null,
                colorDepth: (screen && screen.colorDepth)   || null,
                pixelDepth: (screen && screen.pixelDepth)   || null
              },
              window: {
                devicePixelRatio: window.devicePixelRatio || null,
                outerWidth: window.outerWidth || null,
                outerHeight: window.outerHeight || null,
                innerWidth: window.innerWidth || null,
                innerHeight: window.innerHeight || null,
                pageXOffset: window.pageXOffset || 0,
                pageYOffset: window.pageYOffset || 0
              },
              visualViewport: {
                width: vv.width || null,
                height: vv.height || null,
                scale: vv.scale || null,
                offsetLeft: vv.offsetLeft || null,
                offsetTop: vv.offsetTop || null,
                pageLeft: vv.pageLeft || null,
                pageTop: vv.pageTop || null
              },
              documentElement: {
                clientWidth:  docEl.clientWidth || null,
                clientHeight: docEl.clientHeight || null,
                scrollWidth:  docEl.scrollWidth || null,
                scrollHeight: docEl.scrollHeight || null
              }
            };
          } catch (e) { return null; }
        })();
        """
        return self._safe_js(browser, js) or {}

    def _detect_scroll_container(self, browser: WebDriver, selectors: List[str]) -> Dict[str, Any]:
        info = {
            "matched_selector": None,
            "clientHeight": None,
            "scrollHeight": None,
            "scrollTop": None
        }
        for sel in selectors:
            try:
                els = browser.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                els = []
            if els:
                el = els[0]
                info["matched_selector"] = sel
                try:
                    info["clientHeight"] = int(browser.execute_script("return arguments[0].clientHeight", el))
                    info["scrollHeight"] = int(browser.execute_script("return arguments[0].scrollHeight", el))
                    info["scrollTop"]    = int(browser.execute_script("return arguments[0].scrollTop", el))
                except Exception:
                    pass
                return info

        # Фолбэк: <html> как контейнер
        try:
            html = browser.find_element(By.TAG_NAME, "html")
            info["matched_selector"] = "<html>"
            info["clientHeight"] = int(browser.execute_script("return arguments[0].clientHeight", html))
            info["scrollHeight"] = int(browser.execute_script("return arguments[0].scrollHeight", html))
            info["scrollTop"]    = int(browser.execute_script("return arguments[0].scrollTop", html))
        except Exception:
            pass
        return info

    def _measure_headers(self, browser: WebDriver) -> Dict[str, Any]:
        js = """
        (() => {
          try {
            const q = (s)=>document.querySelector(s);
            const a = q('.header-container.app-navigation');
            const b = q('.Header.DashboardHeader.shadow-1[data-screen-structure="header-block"]');
            const ha = a ? Math.round(a.getBoundingClientRect().height) : 0;
            const hb = b ? Math.round(b.getBoundingClientRect().height) : 0;
            return { header_app_nav: ha, header_dashboard: hb, header_total: ha + hb };
          } catch (e) { return { header_app_nav:0, header_dashboard:0, header_total:0 }; }
        })();
        """
        return self._safe_js(browser, js) or {"header_app_nav": 0, "header_dashboard": 0, "header_total": 0}

    def _take_tiny_screenshot(self, browser: WebDriver, prefix: str) -> Tuple[str, Optional[int], Optional[int]]:
        """
        Делает крошечный скрин, читает его размер через PIL и возвращает (путь, W, H).
        """
        from PIL import Image
        path = os.path.join(self.temp_dir, f"{prefix}_tiny.png")
        try:
            browser.save_screenshot(path)
            with Image.open(path) as im:
                w, h = im.size
            return path, w, h
        except Exception:
            return path, None, None

    def _log_brief(self, snap: Dict[str, Any], logger) -> None:
        win = snap.get("window", {})
        scr = snap.get("screen", {})
        vv  = snap.get("visualViewport", {})
        sc  = snap.get("selectedScrollContainer", {})
        hdr = snap.get("headers", {})
        kf  = snap.get("k_factors", {})

        lines = [
            "[DIAG] --- ENV SNAPSHOT ---",
            f"userAgent: {snap.get('navigator',{}).get('userAgent')}",
            f"screen: {scr.get('width')} x {scr.get('height')} (avail {scr.get('availWidth')}x{scr.get('availHeight')})",
            f"window: outer={win.get('outerWidth')}x{win.get('outerHeight')}, inner={win.get('innerWidth')}x{win.get('innerHeight')}, dpr={win.get('devicePixelRatio')}",
            f"visualViewport: size={vv.get('width')}x{vv.get('height')}, scale={vv.get('scale')}",
            f"documentElement: client={snap.get('documentElement',{}).get('clientWidth')}x{snap.get('documentElement',{}).get('clientHeight')}",
            f"scrollContainer: sel='{sc.get('matched_selector')}', clientH={sc.get('clientHeight')}, scrollH={sc.get('scrollHeight')}",
            f"headers: app_nav={hdr.get('header_app_nav')}, dashboard={hdr.get('header_dashboard')}, total={hdr.get('header_total')}",
            f"bitmap: {snap.get('bitmapScreenshot',{}).get('bitmap_width')} x {snap.get('bitmapScreenshot',{}).get('bitmap_height')}",
            f"k_factors: window_inner={kf.get('k_from_window_inner')}, scroll_client={kf.get('k_from_scroll_client')}",
        ]
        for ln in lines:
            _log(logger, ln)


# ===================== ВСПОМОГАТЕЛЬНОЕ =====================

def _delta(a, b):
    try:
        if a is None or b is None:
            return None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return round(b - a, 4)
        return None
    except Exception:
        return None


def _dig(d: Optional[Dict[str, Any]], *path):
    cur = d or {}
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _log(logger, msg: str, level: str = "info"):
    if logger is None:
        print(msg)
        return
    if level == "error":
        logger.error(msg)
    elif level == "warning":
        logger.warning(msg)
    else:
        logger.info(msg)
