from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.utils import platform
import json
import os

# ========== 常數設定 ==========
FONT_NAME = "NotoTC"
PRIZES_PER_ROW = 3
SAVE_DELAY = 0.4  # 秒，避免每次操作都寫檔

# ---- ICON 設定 ----
ICON_FILE = "CASH.png"  # 圖示檔名（置於程式同目錄）

# ---- 統一字體大小（sp：隨螢幕密度與使用者字級縮放） ----
FONT_SIZE_TITLE   = sp(20)   # 主標題
FONT_SIZE_HEADER  = sp(13)   # 表頭
FONT_SIZE_BANK    = sp(12)   # 銀行名稱
FONT_SIZE_SPINNER = sp(12)   # 下拉選單
FONT_SIZE_ROW     = sp(12)   # 本行合計
FONT_SIZE_TOTAL   = sp(17)   # 底部總計
FONT_SIZE_BUTTON  = sp(13)   # 按鈕

# ---- 尺寸（dp：隨螢幕密度縮放） ----
ROW_HEIGHT     = dp(72)   # 每行銀行列高度
HEADER_HEIGHT  = dp(40)   # 表頭高度
TITLE_BAR_HINT = 0.07     # 標題列佔比
TOTAL_HINT     = 0.08     # 底部總計佔比
LAYOUT_SPACING = dp(8)
LAYOUT_PADDING = dp(12)

prize_map = {
    "10元": {"per": 10, "count": 3},
    "20元": {"per": 20, "count": 3},
    "50元": {"per": 50, "count": 3},
    "100元": {"per": 100, "count": 3},
    "200元": {"per": 200, "count": 3},
    "100-12": {"per": 100, "count": 1},
}
amount_options = list(prize_map.keys())
spinner_values = ["未選擇"] + amount_options

bank_list = [
    "中國銀行", "大豐銀行", "支付寶", "廣發銀行",
    "國際銀行", "工商銀行", "M pay", "Ue pay",
]

# ========== 字型設定 ==========
LabelBase.register(name=FONT_NAME, fn_regular="NotoSansTC-Regular.ttf")

# 僅在桌面除錯時設定視窗大小；手機上由系統決定
if platform not in ("android", "ios"):
    Window.size = (720, 900)


def get_record_file() -> str:
    """取得可寫入的存檔路徑（Android 上使用 App 私有目錄）"""
    try:
        app = App.get_running_app()
        base = app.user_data_dir if app else "."
    except Exception:
        base = "."
    return os.path.join(base, "record.json")


def calculate_prize_total(spinner_text: str, checked: bool) -> int:
    """計算單一抽獎項目的金額（未選擇或已勾選 = 0）"""
    if spinner_text == "未選擇" or checked:
        return 0
    data = prize_map.get(spinner_text)
    return data["per"] * data["count"] if data else 0


class PrizeItem(BoxLayout):
    """單一個抽獎項目：下拉 + 核取方塊"""
    def __init__(self, on_change, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(2)
        self.size_hint_x = 0.18
        self._on_change = on_change

        self.spinner = Spinner(
            text="未選擇", values=spinner_values,
            font_name=FONT_NAME, font_size=FONT_SIZE_SPINNER,
            size_hint_y=0.8,
        )
        self.checkbox = CheckBox(active=False, size_hint_y=0.2)
        self.add_widget(self.spinner)
        self.add_widget(self.checkbox)

        self.spinner.bind(text=self._trigger)
        self.checkbox.bind(active=self._trigger)

    def _trigger(self, *args):
        self._on_change()

    @property
    def value(self) -> int:
        return calculate_prize_total(self.spinner.text, self.checkbox.active)

    def get_data(self):
        return {"spinner": self.spinner.text, "checked": self.checkbox.active}

    def set_data(self, data):
        self.spinner.text = data.get("spinner", "未選擇")
        self.checkbox.active = data.get("checked", False)


class BankRow(BoxLayout):
    def __init__(self, bank_name, on_modify, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.spacing = dp(4)
        self.size_hint_y = None
        self.height = ROW_HEIGHT
        self.bank_name = bank_name
        self._on_modify = on_modify

        self.add_widget(Label(
            text=bank_name, size_hint_x=0.14,
            font_name=FONT_NAME, font_size=FONT_SIZE_BANK,
        ))

        self.prizes = [
            PrizeItem(on_change=self._handle_change) for _ in range(PRIZES_PER_ROW)
        ]
        for item in self.prizes:
            self.add_widget(item)

        self.result_label = Label(
            text="本行：0 元", size_hint_x=0.22,
            font_name=FONT_NAME, font_size=FONT_SIZE_ROW,
        )
        self.add_widget(self.result_label)

    def _handle_change(self):
        self.recalc()
        self._on_modify()

    def total(self) -> int:
        return sum(item.value for item in self.prizes)

    def recalc(self):
        self.result_label.text = f"本行：{self.total()} 元"

    def get_data(self):
        return {
            "bank": self.bank_name,
            "prizes": [p.get_data() for p in self.prizes],
        }

    def set_data(self, data):
        for idx, p_data in enumerate(data.get("prizes", [])):
            if idx < len(self.prizes):
                self.prizes[idx].set_data(p_data)
        self.recalc()


class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = LAYOUT_SPACING
        self.padding = LAYOUT_PADDING
        self.bank_rows = []
        self._save_event = None  # 延遲儲存用

        self._build_ui()
        self.load_data()
        self._update_total()

    def _build_ui(self):
        # 標題列 + 重置按鈕
        title_bar = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(4),
        )
        title_bar.add_widget(Label(
            text="澳門連環消費大獎賞記錄簿",
            font_name=FONT_NAME, font_size=FONT_SIZE_TITLE,
        ))
        reset_btn = Button(
            text="重置全部", font_name=FONT_NAME,
            font_size=FONT_SIZE_BUTTON, size_hint_x=0.3,
        )
        reset_btn.bind(on_press=self.reset_all)
        title_bar.add_widget(reset_btn)
        self.add_widget(title_bar)

        # 表頭
        header = BoxLayout(
            orientation="horizontal", spacing=dp(4),
            size_hint_y=None, height=HEADER_HEIGHT,
        )
        headers = [
            ("銀行", 0.14),
            ("抽獎1\n(勾選=已用)", 0.18),
            ("抽獎2\n(勾選=已用)", 0.18),
            ("抽獎3\n(勾選=已用)", 0.18),
            ("本行所需金額", 0.22),
        ]
        for text, width in headers:
            header.add_widget(Label(
                text=text, size_hint_x=width,
                font_name=FONT_NAME, font_size=FONT_SIZE_HEADER, bold=True,
            ))
        self.add_widget(header)

        # 銀行列
        for bank in bank_list:
            row = BankRow(bank, on_modify=self._on_row_modified)
            self.bank_rows.append(row)
            self.add_widget(row)

        # 底部總計
        self.total_label = Label(
            text="【全部銀行合計：0 元】",
            font_name=FONT_NAME, font_size=FONT_SIZE_TOTAL,
            size_hint_y=None, height=dp(48),
        )
        self.add_widget(self.total_label)

    def _on_row_modified(self):
        self._update_total()
        self._schedule_save()

    def _update_total(self):
        total = sum(row.total() for row in self.bank_rows)
        self.total_label.text = f"【全部銀行合計：{total} 元】"

    def _schedule_save(self):
        """延遲存檔，避免每次操作都觸發寫檔"""
        if self._save_event is not None:
            self._save_event.cancel()
        self._save_event = Clock.schedule_once(lambda dt: self.save_data(), SAVE_DELAY)

    def save_data(self, *args):
        self._save_event = None
        data = [row.get_data() for row in self.bank_rows]
        record_file = get_record_file()
        try:
            tmp = record_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, record_file)  # 原子寫入，避免檔案損毀
        except Exception as e:
            print(f"儲存失敗：{e}")

    def load_data(self):
        record_file = get_record_file()
        if not os.path.exists(record_file):
            return
        try:
            with open(record_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for idx, row_data in enumerate(data):
                if idx < len(self.bank_rows):
                    self.bank_rows[idx].set_data(row_data)
        except Exception as e:
            print(f"讀取紀錄失敗：{e}")

    def reset_all(self, inst):
        for row in self.bank_rows:
            for item in row.prizes:
                item.spinner.text = "未選擇"
                item.checkbox.active = False
        self._update_total()
        # 重置後立即存檔
        if self._save_event is not None:
            self._save_event.cancel()
            self._save_event = None
        self.save_data()


class PrizeCalcApp(App):
    def build(self):
        self.title = "連環消費記錄簿"
        # 設定視窗 ICON（檔案不存在時忽略，不影響程式執行）
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ICON_FILE)
        if not os.path.exists(icon_path):
            icon_path = ICON_FILE
        try:
            Window.set_icon(icon_path)
        except Exception as e:
            print(f"設定 ICON 失敗：{e}")
        return MainLayout()


if __name__ == "__main__":
    PrizeCalcApp().run()