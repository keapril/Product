"""
產品資料查詢系統 - 改善版 v2.0
改善項目：效能優化、程式碼品質
"""

import flet as ft
import csv
import io
import math
import time
import threading
import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

# -----------------------------------------------------------------------------
# 日誌設定
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 設定 (Constants & Theme)
# -----------------------------------------------------------------------------
COLOR_BG = "#F9F8F4"       # 米白背景
COLOR_PRIMARY = "#7A8B7D"  # 莫蘭迪綠
COLOR_TEXT_MAIN = "#5C5C5C"
COLOR_TEXT_SUB = "#8C8680"
ITEMS_PER_PAGE = 20
DEBOUNCE_DELAY = 0.3  # 搜尋延遲秒數


# -----------------------------------------------------------------------------
# Enum 定義（取代 magic string）
# -----------------------------------------------------------------------------
class TabName(Enum):
    """頁籤名稱"""
    SEARCH = "search"
    ADMIN = "admin"


class SortOrder(Enum):
    """排序方向"""
    ASC = "asc"
    DESC = "desc"


# -----------------------------------------------------------------------------
# 資料類別
# -----------------------------------------------------------------------------
@dataclass
class ProductItem:
    """產品資料結構"""
    id: int
    code: str
    categoryName: str
    name: str
    spec: str
    udi: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "categoryName": self.categoryName,
            "name": self.name,
            "spec": self.spec,
            "udi": self.udi
        }

    @staticmethod
    def from_dict(data: dict) -> "ProductItem":
        return ProductItem(
            id=data.get("id", 0),
            code=data.get("code", ""),
            categoryName=data.get("categoryName", ""),
            name=data.get("name", ""),
            spec=data.get("spec", ""),
            udi=data.get("udi", "")
        )


# -----------------------------------------------------------------------------
# 預設範例資料
# -----------------------------------------------------------------------------
DEFAULT_DATA = [
    {"id": 1, "code": "0137NE", "categoryName": "Syringes", "name": "Perouse Perouse Syringes 150ml", "spec": "", "udi": ""},
    {"id": 2, "code": "0163NA", "categoryName": "High Pressure Tubing", "name": "Perouse HighPressure Line 50cm", "spec": "1.8mm", "udi": ""},
    {"id": 3, "code": "0163ND", "categoryName": "High Pressure Tubing", "name": "Perouse HighPressure Line120cm", "spec": "", "udi": ""},
    {"id": 4, "code": "0185NA", "categoryName": "Inflation Device", "name": "Perouse Inflation Device 30atm", "spec": "", "udi": ""},
]


# -----------------------------------------------------------------------------
# 主應用程式
# -----------------------------------------------------------------------------
class ProductApp:
    """產品查詢系統主應用程式（統一架構版）"""

    def __init__(self, page: ft.Page):
        self.page = page
        self._setup_page()
        self._init_state()
        self._load_data()
        self._build_search_index()
        self._init_ui()

    # =========================================================================
    # 初始化方法
    # =========================================================================
    def _setup_page(self):
        """設定頁面基本屬性"""
        self.page.title = "產品資料查詢系統"
        self.page.bgcolor = COLOR_BG
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 20
        self.page.fonts = {
            "NotoSerif": "https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@300;400;600&display=swap"
        }
        self.page.theme = ft.Theme(font_family="NotoSerif")

    def _init_state(self):
        """初始化狀態變數"""
        self.all_data: List[dict] = []
        self.filtered_data: List[dict] = []
        self.search_index: dict = {}  # 搜尋索引
        self.current_page: int = 1
        self.search_term: str = ""
        self.debounce_timer: Optional[threading.Timer] = None
        self.current_tab: TabName = TabName.SEARCH

    def _load_data(self):
        """從 Client Storage 讀取資料"""
        try:
            stored_data = self.page.client_storage.get("product_data")
            if stored_data:
                self.all_data = stored_data
                logger.info(f"已從 Storage 載入 {len(self.all_data)} 筆資料")
            else:
                self.all_data = DEFAULT_DATA.copy()
                logger.info("使用預設資料")
        except Exception as e:
            logger.warning(f"讀取 Storage 失敗: {e}")
            self.all_data = DEFAULT_DATA.copy()

        # 初始不顯示搜尋結果（效能優化）
        self.filtered_data = []

    def _save_data(self):
        """存入 Client Storage"""
        try:
            self.page.client_storage.set("product_data", self.all_data)
            logger.info(f"成功儲存 {len(self.all_data)} 筆資料")
        except PermissionError:
            logger.error("Storage 權限不足")
            self._show_snack("儲存失敗：權限不足", False)
        except Exception as e:
            logger.exception(f"Storage 錯誤: {e}")
            self._show_snack(f"儲存失敗：{str(e)}", False)

    # =========================================================================
    # 效能優化：搜尋索引
    # =========================================================================
    def _build_search_index(self):
        """建立搜尋索引以加速查詢"""
        self.search_index = {}
        for item in self.all_data:
            # 合併所有可搜尋欄位
            searchable_text = f"{item['code']} {item['name']} {item['spec']}".lower()

            # 以空白分割建立索引
            for word in searchable_text.split():
                if word not in self.search_index:
                    self.search_index[word] = []
                if item not in self.search_index[word]:
                    self.search_index[word].append(item)

            # 同時支援前綴匹配（更彈性的搜尋）
            self._add_prefix_index(item, searchable_text)

        logger.info(f"搜尋索引建立完成，共 {len(self.search_index)} 個詞條")

    def _add_prefix_index(self, item: dict, text: str):
        """為前綴搜尋建立索引"""
        # 針對 code, name, spec 的開頭建立前綴索引
        for key in ['code', 'name', 'spec']:
            value = str(item.get(key, '')).lower()
            for i in range(1, min(len(value) + 1, 10)):  # 最多取前 10 字元
                prefix = value[:i]
                prefix_key = f"_prefix_{prefix}"
                if prefix_key not in self.search_index:
                    self.search_index[prefix_key] = []
                if item not in self.search_index[prefix_key]:
                    self.search_index[prefix_key].append(item)

    def _search_with_index(self, term: str) -> List[dict]:
        """使用索引進行搜尋"""
        term_lower = term.lower().strip()

        if not term_lower:
            return []

        # 先嘗試前綴匹配
        prefix_key = f"_prefix_{term_lower}"
        if prefix_key in self.search_index:
            return self.search_index[prefix_key]

        # 再嘗試完整詞匹配
        if term_lower in self.search_index:
            return self.search_index[term_lower]

        # 最後用傳統方式搜尋（保底）
        return [
            row for row in self.all_data
            if term_lower in str(row['code']).lower() or
               term_lower in str(row['name']).lower() or
               term_lower in str(row['spec']).lower()
        ]

    # =========================================================================
    # UI 建構
    # =========================================================================
    def _init_ui(self):
        """初始化所有 UI 元件"""
        self._build_navbar()
        self._build_search_view()
        self._build_admin_view()
        self._assemble_page()

    def _build_navbar(self):
        """建立導覽列"""
        self.nav_search = ft.TextButton(
            "查詢",
            on_click=lambda _: self._switch_tab(TabName.SEARCH),
            style=self._get_nav_style(True)
        )
        self.nav_admin = ft.TextButton(
            "管理",
            on_click=lambda _: self._switch_tab(TabName.ADMIN),
            style=self._get_nav_style(False)
        )

        logo = ft.Container(
            content=ft.Text("P", font_family="Serif", weight=ft.FontWeight.BOLD,
                          color="#F9F8F4", italic=True),
            bgcolor=COLOR_PRIMARY, width=32, height=32, border_radius=16,
            alignment=ft.alignment.center
        )

        self.navbar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Row([
                        logo,
                        ft.Text("產品資料查詢系統", size=18, weight=ft.FontWeight.BOLD,
                               color=COLOR_TEXT_MAIN, letter_spacing=2),
                    ]),
                    ft.Row([self.nav_search, self.nav_admin])
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=ft.padding.symmetric(vertical=10, horizontal=20),
            bgcolor=ft.Colors.WHITE.with_opacity(0.9),
            border=ft.border.only(bottom=ft.BorderSide(1, "#E5E0D8")),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=10,
                               color=ft.Colors.BLACK12, offset=ft.Offset(0, 2))
        )

    def _build_search_view(self):
        """建立搜尋頁面"""
        # 搜尋輸入框
        self.search_field = ft.TextField(
            hint_text="請輸入關鍵字搜尋 (代碼、品名、規格)...",
            width=500,
            text_align=ft.TextAlign.CENTER,
            border_color="#B0A8A0",
            focused_border_color=COLOR_PRIMARY,
            text_style=ft.TextStyle(color=COLOR_TEXT_MAIN),
            on_change=self._on_search_change,
            prefix_icon=ft.Icons.SEARCH,
            suffix=ft.IconButton(ft.Icons.CLOSE, icon_size=16,
                                on_click=self._clear_search, icon_color="#B0A8A0")
        )

        # 資料表格
        self.data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("產品代碼", size=13, color=COLOR_TEXT_SUB)),
                ft.DataColumn(ft.Text("類別名稱", size=13, color=COLOR_TEXT_SUB)),
                ft.DataColumn(ft.Text("品名", size=13, color=COLOR_TEXT_SUB)),
                ft.DataColumn(ft.Text("規格", size=13, color=COLOR_TEXT_SUB)),
                ft.DataColumn(ft.Text("UDI", size=13, color=COLOR_TEXT_SUB)),
            ],
            width=1000,
            heading_row_color="#F9F8F4",
            data_row_max_height=float("inf"),
        )

        # 分頁控制（獨立命名）
        self.pagination_controls = ft.Row(alignment=ft.MainAxisAlignment.CENTER)

        # 狀態文字（獨立命名）
        self.status_text = ft.Text("請輸入搜尋條件", color=COLOR_TEXT_SUB, size=14)

        # 資料庫筆數文字（獨立命名）
        self.db_count_text = ft.Text(
            f"目前資料庫：{len(self.all_data)} 筆紀錄",
            color=COLOR_TEXT_SUB,
            italic=True
        )

        # 組裝搜尋視圖
        self.search_view = ft.Column(
            controls=[
                ft.Container(height=20),
                ft.Column([
                    ft.Text("產品目錄", size=30, color=COLOR_TEXT_MAIN,
                           text_align=ft.TextAlign.CENTER),
                    ft.Divider(color="#DCD6CE", thickness=1, height=20),
                    self.db_count_text,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(content=self.search_field, alignment=ft.alignment.center,
                            padding=20),
                ft.Container(
                    content=ft.Column([
                        self.data_table,
                        ft.Container(height=20),
                        self.pagination_controls,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=ft.Colors.WHITE.with_opacity(0.6),
                    padding=20,
                    border_radius=10,
                    border=ft.border.all(1, "#E5E0D8"),
                    alignment=ft.alignment.center
                ),
                ft.Container(content=self.status_text, alignment=ft.alignment.center,
                            padding=20)
            ],
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            visible=True
        )

    def _build_admin_view(self):
        """建立管理頁面"""
        # CSV 輸入區
        self.csv_input = ft.TextField(
            multiline=True,
            min_lines=10,
            max_lines=15,
            hint_text="請將 Excel/CSV 內容全選複製，貼於此處...",
            text_size=12,
            border_color="#CFC8C0"
        )

        upload_area = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.PASTE_OUTLINED, size=50, color=COLOR_TEXT_SUB),
                ft.Text("直接貼上 CSV 內容", color=COLOR_TEXT_MAIN),
                self.csv_input,
                ft.Container(height=10),
                ft.ElevatedButton(
                    "確認匯入",
                    bgcolor=COLOR_PRIMARY,
                    color="white",
                    on_click=self._on_paste_import
                ),
                ft.Container(height=20),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Container(width=4, height=4, bgcolor=COLOR_PRIMARY,
                                        border_radius=2),
                            ft.Text("注意事項", size=12, color=COLOR_PRIMARY)
                        ]),
                        ft.Text(
                            "僅讀取前 5 欄：代碼、分類、類別、品名、規格\n"
                            "系統過濾 'ZZ' 或 '待' 開頭項目",
                            size=12, color=COLOR_TEXT_SUB
                        )
                    ]),
                    bgcolor="#F5F2EF", padding=15, border_radius=5
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=30,
            border=ft.border.all(1, "#CFC8C0"),
            border_radius=10,
            bgcolor="#FAF9F7",
        )

        self.admin_view = ft.Column(
            controls=[
                ft.Container(height=30),
                ft.Text("資料維護", size=24, color=COLOR_TEXT_MAIN),
                ft.Divider(width=50, color="#DCD6CE"),
                ft.Text("Update Database", color=COLOR_TEXT_SUB, size=12),
                ft.Container(height=20),
                upload_area,
                ft.Container(height=20),
                ft.OutlinedButton(
                    "清除所有資料",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=self._clear_data,
                    style=ft.ButtonStyle(color="red")
                )
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            visible=False
        )

    def _assemble_page(self):
        """組合主畫面"""
        self.page.add(
            self.navbar,
            ft.Container(
                content=ft.Stack([self.search_view, self.admin_view]),
                expand=True,
                padding=ft.padding.symmetric(horizontal=20)
            )
        )

    # =========================================================================
    # 導覽邏輯
    # =========================================================================
    def _get_nav_style(self, is_active: bool) -> ft.ButtonStyle:
        """取得導覽按鈕樣式"""
        return ft.ButtonStyle(
            color=COLOR_TEXT_MAIN if is_active else COLOR_TEXT_SUB,
            overlay_color=ft.Colors.TRANSPARENT,
            side=ft.BorderSide(0, ft.Colors.TRANSPARENT)
        )

    def _switch_tab(self, tab: TabName):
        """切換頁籤"""
        self.current_tab = tab
        is_search = tab == TabName.SEARCH

        self.search_view.visible = is_search
        self.admin_view.visible = not is_search

        # 更新導覽樣式
        self.nav_search.style = self._get_nav_style(is_search)
        self.nav_admin.style = self._get_nav_style(not is_search)

        self.page.update()

    # =========================================================================
    # 效能優化：Debounce 搜尋
    # =========================================================================
    def _on_search_change(self, e):
        """搜尋輸入變更（帶 Debounce）"""
        # 取消前一個計時器
        if self.debounce_timer:
            self.debounce_timer.cancel()

        self.search_term = e.control.value

        # 設定新的延遲計時器
        self.debounce_timer = threading.Timer(
            DEBOUNCE_DELAY,
            self._debounced_search
        )
        self.debounce_timer.start()

    def _debounced_search(self):
        """延遲後執行的搜尋"""
        self._perform_search()
        self.page.update()

    def _clear_search(self, e):
        """清除搜尋"""
        self.search_field.value = ""
        self.search_term = ""
        self._perform_search()
        self.page.update()

    def _perform_search(self):
        """執行搜尋"""
        term = self.search_term.lower().strip()

        if not term:
            self.filtered_data = []
            self.status_text.value = "請輸入搜尋條件"
            self.status_text.visible = True
            self.data_table.visible = False
            self.pagination_controls.visible = False
        else:
            # 使用索引加速搜尋
            self.filtered_data = self._search_with_index(term)
            self.current_page = 1
            self.status_text.visible = not self.filtered_data
            self.status_text.value = "查無資料" if not self.filtered_data else ""
            self.data_table.visible = True
            self.pagination_controls.visible = True

        self._render_table()

    # =========================================================================
    # 表格渲染
    # =========================================================================
    def _render_table(self):
        """渲染表格內容"""
        if not self.filtered_data:
            self.data_table.rows = []
            self._render_pagination()
            return

        start = (self.current_page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        page_data = self.filtered_data[start:end]

        self.data_table.rows = []
        for item in page_data:
            self.data_table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(item['code'], font_family="Monospace",
                                       color=COLOR_TEXT_MAIN)),
                    ft.DataCell(ft.Container(
                        content=ft.Text(item['categoryName'], size=12, color=COLOR_PRIMARY),
                        bgcolor="#F5F2EF", padding=5, border_radius=10
                    )),
                    ft.DataCell(ft.Text(item['name'], size=12, color=COLOR_TEXT_MAIN,
                                       width=300, no_wrap=False)),
                    ft.DataCell(ft.Text(item['spec'] or "-", size=12,
                                       color=COLOR_TEXT_SUB, width=150, no_wrap=False)),
                    ft.DataCell(ft.Text(item['udi'], size=12, color="#B0A8A0")),
                ])
            )

        self._render_pagination()

    def _render_pagination(self):
        """渲染分頁控制"""
        total_pages = math.ceil(len(self.filtered_data) / ITEMS_PER_PAGE)
        if total_pages <= 1:
            self.pagination_controls.visible = False
            return

        self.pagination_controls.visible = True
        self.pagination_controls.controls = [
            ft.IconButton(
                ft.Icons.CHEVRON_LEFT,
                on_click=lambda _: self._change_page(-1),
                disabled=self.current_page == 1
            ),
            ft.Text(f"第 {self.current_page} 頁 / 共 {total_pages} 頁",
                   size=12, color=COLOR_TEXT_SUB),
            ft.IconButton(
                ft.Icons.CHEVRON_RIGHT,
                on_click=lambda _: self._change_page(1),
                disabled=self.current_page == total_pages
            )
        ]

    def _change_page(self, delta: int):
        """切換分頁"""
        total_pages = math.ceil(len(self.filtered_data) / ITEMS_PER_PAGE)
        new_page = self.current_page + delta
        if 1 <= new_page <= total_pages:
            self.current_page = new_page
            self._render_table()
            self.page.update()

    # =========================================================================
    # CSV 匯入
    # =========================================================================
    def _on_paste_import(self, e):
        """處理貼上匯入"""
        content = self.csv_input.value
        if not content:
            self._show_snack("請先貼上內容", False)
            return

        self._process_csv_content(content)
        self.csv_input.value = ""
        self._switch_tab(TabName.SEARCH)

    def _process_csv_content(self, text_content: str):
        """解析 CSV 字串"""
        lines = text_content.splitlines()
        parsed_data = []

        try:
            reader = csv.reader(lines)
            next(reader, None)  # 跳過標題

            for idx, row in enumerate(reader, 1):
                if len(row) < 5:
                    continue

                code = row[0].strip()
                # 過濾邏輯
                if code.upper().startswith("ZZ") or code.startswith("待"):
                    continue

                parsed_data.append({
                    "id": idx,
                    "code": code,
                    "categoryName": row[2].strip(),
                    "name": row[3].strip(),
                    "spec": row[4].strip(),
                    "udi": ""
                })

            if parsed_data:
                self.all_data = parsed_data
                self._save_data()
                self._build_search_index()  # 重建索引
                self._show_snack(f"成功匯入 {len(parsed_data)} 筆資料", True)
                # 更新 UI（使用獨立命名的元件）
                self.db_count_text.value = f"目前資料庫：{len(self.all_data)} 筆紀錄"
            else:
                self._show_snack("無有效資料", False)

        except Exception as e:
            logger.exception(f"CSV 解析錯誤: {e}")
            self._show_snack(f"解析錯誤: {str(e)}", False)

    def _clear_data(self, e):
        """清除所有資料"""
        self.all_data = DEFAULT_DATA.copy()
        self._save_data()
        self._build_search_index()  # 重建索引
        self.db_count_text.value = f"目前資料庫：{len(self.all_data)} 筆紀錄"
        self._show_snack("資料已重置", True)
        self.page.update()

    def _show_snack(self, msg: str, is_success: bool):
        """顯示提示訊息"""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(msg),
            bgcolor=COLOR_PRIMARY if is_success else "red"
        )
        self.page.snack_bar.open = True
        self.page.update()


# -----------------------------------------------------------------------------
# 啟動
# -----------------------------------------------------------------------------
def main(page: ft.Page):
    app = ProductApp(page)


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
