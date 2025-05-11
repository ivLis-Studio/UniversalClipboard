import os
import json

# --- 설정 파일 관련 상수 ---
CONFIG_FILE = "clipboard_manager_config.json"
DEFAULT_HOTKEY_CONFIG = {"modifiers": ["ctrl_l", "shift_l"], "key": "v"}
MAX_HISTORY_ITEMS = 50
CLIP_PREVIEW_MAX_LEN = 120 # 미리보기 길이 증가

def load_config():
    """
    설정 파일을 로드하는 함수
    설정 파일이 없거나 손상된 경우 기본값 반환
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                if "hotkey" not in config:
                    config["hotkey"] = DEFAULT_HOTKEY_CONFIG.copy()
                if "history" not in config:
                    config["history"] = []
                return config
        except json.JSONDecodeError:
            print(f"Error decoding {CONFIG_FILE}, using defaults.")
    return {"hotkey": DEFAULT_HOTKEY_CONFIG.copy(), "history": []}

def save_config(config_data):
    """
    설정 데이터를 파일에 저장하는 함수
    """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config to {CONFIG_FILE}: {e}")

def format_hotkey_for_display(config):
    """
    단축키 설정을 사용자가 읽기 쉬운 형식으로 변환
    """
    if not config or not config.get("key"):
        return "설정되지 않음"
    
    mods = []
    key_str = config["key"]
    
    for mod_name in config.get("modifiers", []):
        name = mod_name.replace('_l', '').replace('_r', '').replace('cmd', 'Cmd').capitalize()
        mods.append(name)
    
    if isinstance(key_str, str): 
        if '\x00' < key_str < '\x20':  # 컨트롤 문자인 경우
            key_str = f"Ctrl+{chr(ord(key_str) + ord('A') -1)}" if '\x01' <= key_str <= '\x1A' else repr(key_str)
        else:
            key_str = key_str.upper() if len(key_str) == 1 else key_str.capitalize()
    
    return " + ".join(mods + [key_str]) 