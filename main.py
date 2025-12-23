import flet as ft
import csv
import io
import math
import time
import json

# -----------------------------------------------------------------------------
# 設定 (Constants & Theme)
# -----------------------------------------------------------------------------
COLOR_BG = "#F9F8F4"       # 米白背景
COLOR_PRIMARY = "#7A8B7D"  # 莫蘭迪綠
COLOR_TEXT_MAIN = "#5C5C5C"
COLOR_TEXT_SUB = "#8C8680"
ITEMS_PER_PAGE = 20

# 預設範例資料
DEFAULT_DATA = [
    {"id": 1, "code": "0137NE", "categoryName": "Syringes", "name": "Perouse Perouse Syringes 150ml", "spec": "", "udi": ""},
    {"id": 2, "code": "0163NA", "categoryName": "High Pressure Tubing", "name": "Perouse HighPressure Line 50cm", "spec": "1.8mm", "udi": ""},
    {"id": 3, "code": "0163ND", "categoryName": "High Pressure Tubing", "name": "Perouse HighPressure Line120cm", "spec": "", "udi": ""},
    {"id": 4, "code": "0185NA", "categoryName": "Inflation Device", "name": "Perouse Inflation Device 30atm", "spec": "", "udi": ""},
]

class ProductApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "產品資料查詢系統"
        self.page.bgcolor = COLOR_BG
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 20
        self.page.fonts = {
            "NotoSerif": "https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@300;400;600&display=swap"
        }
        self.page.theme = ft.Theme(font_family="NotoSerif")
        
        # 資料狀態
        self.all_data = []
        self.filtered_data = []
        self.current_page = 1
        self.search_term = ""
        self.debounce_timer = None
        
        # 嘗試載入資料
        self.load_data_from_storage()
        
        # 初始化 UI 元件
        self.init_ui()

    def load_data_from_storage(self):
        """從 Client Storage 讀取資料"""
        try:
            stored_data = self.page.client_storage.get("product_data")
            if stored_data:
                self.all_data = stored_data
            else:
                self.all_data = DEFAULT_DATA.copy()
        except Exception:
            self.all_data = DEFAULT_DATA.copy()
        
        # 初始不顯示搜尋結果 (效能優化邏輯)
        self.filtered_data = [] 

    def save_data_to_storage(self):
        """存入 Client Storage"""
        try:
            self.page.client_storage.set("product_data", self.all_data)
        except Exception as e:
            print(f"Storage Error: {e}")

    # -------------------------------------------------------------------------
    # UI 建構
    # -------------------------------------------------------------------------
    def init_ui(self):
        # 導覽列
        self.nav_search = ft.TextButton("查詢", on_click=lambda _: self.switch_tab("search"), style=self.get_nav_style(True))
        self.nav_admin = ft.TextButton("管理", on_click=lambda _: self.switch_tab("admin"), style=self.get_nav_style(False))
        
        self.navbar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Row([
                        ft.Container(
                            content=ft.Text("P", font_family="Serif", weight=ft.FontWeight.BOLD, color="#F9F8F4", italic=True),
                            bgcolor=COLOR_PRIMARY, width=32, height=32, border_radius=16, alignment=ft.alignment.center
                        ),
                        ft.Text("產品資料查詢系統", size=18, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_MAIN, letter_spacing=2),
                    ]),
                    ft.Row([self.nav_search, self.nav_admin])
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=ft.padding.symmetric(vertical=10, horizontal=20),
            bgcolor=ft.Colors.WHITE.with_opacity(0.9),
            border=ft.border.only(bottom=ft.BorderSide(1, "#E5E0D8")),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=10, color=ft.Colors.BLACK12, offset=ft.Offset(0, 2))
        )

        # 搜尋頁面元件
        self.search_field = ft.TextField(
            hint_text="請輸入關鍵字搜尋 (代碼、品名、規格)...",
            width=500,
            text_align=ft.TextAlign.CENTER,
            border_color="#B0A8A0",
            focused_border_color=COLOR_PRIMARY,
            text_style=ft.TextStyle(color=COLOR_TEXT_MAIN),
            on_change=self.on_search_change,
            prefix_icon=ft.Icons.SEARCH,
            suffix=ft.IconButton(ft.Icons.CLOSE, icon_size=16, on_click=self.clear_search, icon_color="#B0A8A0")
        )
        
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
            data_row_max_height=float("inf"), # 允許自動長高
        )
        
        self.pagination_controls = ft.Row(alignment=ft.MainAxisAlignment.CENTER)
        self.status_text = ft.Text("請輸入搜尋條件", color=COLOR_TEXT_SUB, size=14)

        self.search_view = ft.Column(
            controls=[
                ft.Container(height=20),
                ft.Column([
                    ft.Text("產品目錄", size=30, color=COLOR_TEXT_MAIN, text_align=ft.TextAlign.CENTER),
                    ft.Divider(color="#DCD6CE", thickness=1, height=20),
                    ft.Text(f"目前資料庫：{len(self.all_data)} 筆紀錄", color=COLOR_TEXT_SUB, italic=True),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(content=self.search_field, alignment=ft.alignment.center, padding=20),
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
                ft.Container(content=self.status_text, alignment=ft.alignment.center, padding=20)
            ],
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            visible=True
        )

        # 管理頁面元件
        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        self.page.overlay.append(self.file_picker)

        self.admin_view = ft.Column(
            controls=[
                ft.Container(height=30),
                ft.Text("資料維護", size=24, color=COLOR_TEXT_MAIN),
                ft.Divider(width=50, color="#DCD6CE"),
                ft.Text("Update Database", color=COLOR_TEXT_SUB, size=12),
                ft.Container(height=20),
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, size=50, color=COLOR_TEXT_SUB),
                        ft.Text("點擊上傳 CSV 檔案", color=COLOR_TEXT_MAIN),
                        ft.ElevatedButton(
                            "選擇檔案", 
                            icon=ft.Icons.FOLDER_OPEN,
                            bgcolor=COLOR_PRIMARY,
                            color="white",
                            on_click=lambda _: self.file_picker.pick_files(allow_multiple=False, allowed_extensions=["csv", "txt"])
                        ),
                        ft.Container(height=20),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([ft.Container(width=4, height=4, bgcolor=COLOR_PRIMARY, border_radius=2), ft.Text("注意事項", size=12, color=COLOR_PRIMARY)]),
                                ft.Text("僅讀取前 5 欄：代碼、分類、類別、品名、規格\n系統將自動略過代碼為 'ZZ' 或 '待' 開頭之項目", size=12, color=COLOR_TEXT_SUB)
                            ]),
                            bgcolor="#F5F2EF", padding=15, border_radius=5
                        )
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=50,
                    border=ft.border.all(1, "#CFC8C0"),
                    border_radius=10,
                    bgcolor="#FAF9F7",
                ),
                ft.Container(height=20),
                ft.OutlinedButton("清除所有資料", icon=ft.Icons.DELETE_OUTLINE, on_click=self.clear_data, style=ft.ButtonStyle(color="red"))
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            visible=False
        )

        # 組合主畫面
        self.page.add(
            self.navbar,
            ft.Container(
                content=ft.Stack([self.search_view, self.admin_view]),
                expand=True,
                padding=ft.padding.symmetric(horizontal=20)
            )
        )

    # -------------------------------------------------------------------------
    # 邏輯處理
    # -------------------------------------------------------------------------
    def get_nav_style(self, is_active):
        return ft.ButtonStyle(
            color=COLOR_TEXT_MAIN if is_active else COLOR_TEXT_SUB,
            overlay_color=ft.Colors.TRANSPARENT,
            side=ft.BorderSide(0, ft.Colors.TRANSPARENT)
        )

    def switch_tab(self, tab_name):
        is_search = tab_name == "search"
        self.search_view.visible = is_search
        self.admin_view.visible = not is_search
        
        # Update Nav Styles
        self.nav_search.style = self.get_nav_style(is_search)
        self.nav_admin.style = self.get_nav_style(not is_search)
        
        # 視覺強調
        if is_search:
            self.nav_search.style = ft.ButtonStyle(color=COLOR_TEXT_MAIN, shape=ft.RoundedRectangleBorder(radius=0)) 
        
        self.page.update()

    def on_search_change(self, e):
        self.search_term = e.control.value
        # 簡單的 Debounce 模擬 (Python sync 模式下無法真正的 async sleep，但在 Flet 中可透過邏輯控制)
        # 這裡為了流暢，直接更新。若資料量極大可考慮 threading timer。
        self.perform_search()

    def clear_search(self, e):
        self.search_field.value = ""
        self.search_term = ""
        self.perform_search()
        self.page.update()

    def perform_search(self):
        term = self.search_term.lower().strip()
        if not term:
            self.filtered_data = []
            self.status_text.value = "請輸入搜尋條件"
            self.status_text.visible = True
            self.data_table.visible = False
            self.pagination_controls.visible = False
        else:
            self.filtered_data = [
                row for row in self.all_data
                if term in str(row['code']).lower() or 
                   term in str(row['name']).lower() or 
                   term in str(row['spec']).lower()
            ]
            self.current_page = 1
            self.status_text.visible = False if self.filtered_data else True
            self.status_text.value = "查無資料" if not self.filtered_data else ""
            self.data_table.visible = True
            self.pagination_controls.visible = True
        
        self.render_table()
        self.page.update()

    def render_table(self):
        if not self.filtered_data:
            self.data_table.rows = []
            self.render_pagination()
            return

        start = (self.current_page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        page_data = self.filtered_data[start:end]

        self.data_table.rows = []
        for item in page_data:
            self.data_table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(item['code'], font_family="Monospace", color=COLOR_TEXT_MAIN)),
                    ft.DataCell(ft.Container(content=ft.Text(item['categoryName'], size=12, color=COLOR_PRIMARY), bgcolor="#F5F2EF", padding=5, border_radius=10)),
                    ft.DataCell(ft.Text(item['name'], size=12, color=COLOR_TEXT_MAIN, width=300, no_wrap=False)), # 允許換行
                    ft.DataCell(ft.Text(item['spec'] or "-", size=12, color=COLOR_TEXT_SUB, width=150, no_wrap=False)),
                    ft.DataCell(ft.Text(item['udi'], size=12, color="#B0A8A0")),
                ])
            )
        
        self.render_pagination()

    def render_pagination(self):
        total_pages = math.ceil(len(self.filtered_data) / ITEMS_PER_PAGE)
        if total_pages <= 1:
            self.pagination_controls.visible = False
            return

        self.pagination_controls.visible = True
        self.pagination_controls.controls = [
            ft.IconButton(
                ft.Icons.CHEVRON_LEFT, 
                on_click=lambda _: self.change_page(-1), 
                disabled=self.current_page == 1
            ),
            ft.Text(f"第 {self.current_page} 頁 / 共 {total_pages} 頁", size=12, color=COLOR_TEXT_SUB),
            ft.IconButton(
                ft.Icons.CHEVRON_RIGHT, 
                on_click=lambda _: self.change_page(1), 
                disabled=self.current_page == total_pages
            )
        ]

    def change_page(self, delta):
        total_pages = math.ceil(len(self.filtered_data) / ITEMS_PER_PAGE)
        new_page = self.current_page + delta
        if 1 <= new_page <= total_pages:
            self.current_page = new_page
            self.render_table()
            self.page.update()

    # -------------------------------------------------------------------------
    # 檔案處理
    # -------------------------------------------------------------------------
    def on_file_picked(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        
        file = e.files[0]
        # Flet Web 模式下讀取檔案內容需要特殊處理，但在 Desktop 模式是路徑
        # 這裡示範通用邏輯 (假設已上傳到記憶體)
        
        # 讀取檔案內容 (需要搭配 upload 邏輯，但在 Flet Desktop 只需 open 路徑)
        # 為了 PWA Web 兼容性，這裡使用 upload 邏輯會比較複雜，
        # 簡化起見，我們假設是在 Desktop 運行，或使用 Flet 的 client uploads
        
        # ⚠️ 注意: 為了讓這個範例簡單可執行，我們假設這是上傳文字內容
        # 在實際 Web PWA 中，Flet 處理 File Upload 會有異步讀取過程
        
        # 這裡模擬讀取：因為 Flet Web 的 FilePicker 回傳的是 UploadFile 物件
        # 我們需要讀取它。
        pass # 實際讀取邏輯需視部署環境而定，以下為 CSV 解析邏輯

    def process_csv_content(self, text_content):
        """解析 CSV 字串"""
        lines = text_content.splitlines()
        parsed_data = []
        try:
            reader = csv.reader(lines)
            header = next(reader, None) # 跳過標題
            
            for idx, row in enumerate(reader, 1):
                if len(row) < 5: continue
                
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
                self.save_data_to_storage()
                self.show_snack(f"成功匯入 {len(parsed_data)} 筆資料", True)
                # 更新 UI
                self.search_view.controls[1].controls[2].value = f"目前資料庫：{len(self.all_data)} 筆紀錄"
            else:
                self.show_snack("無有效資料", False)

        except Exception as e:
            self.show_snack(f"解析錯誤: {str(e)}", False)

    # 為了簡化 PWA 演示，我們修改 FilePicker 為「讀取本地檔案路徑」(Desktop)
    # 若要是純 Web PWA，需要 Flet Upload Handler，這裡改用簡單的 "Paste Text" 替代上傳，保證 PWA 可用性
    # 因為純前端 PWA 讀取本地檔案在 Python 層比較麻煩
    
    def clear_data(self, e):
        self.all_data = DEFAULT_DATA.copy()
        self.save_data_to_storage()
        self.show_snack("資料已重置", True)
        self.page.update()

    def show_snack(self, msg, is_success):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(msg),
            bgcolor=COLOR_PRIMARY if is_success else "red"
        )
        self.page.snack_bar.open = True
        self.page.update()

# -----------------------------------------------------------------------------
# 修正後的 FilePicker 上傳替代方案 (為了 PWA 兼容性)
# -----------------------------------------------------------------------------
# 在 Web PWA 環境下，直接讓 Python 讀取用戶檔案比較複雜。
# 我們用一個 Text Field 讓用戶貼上 CSV 內容來模擬「匯入」，這是最穩定的跨平台解法。

class ImprovedProductApp(ProductApp):
    def init_ui(self):
        super().init_ui()
        
        # 修改 Admin View，加入文字貼上區
        self.csv_input = ft.TextField(
            multiline=True, 
            min_lines=10, 
            max_lines=15, 
            hint_text="請將 Excel/CSV 內容全選複製，貼於此處...",
            text_size=12,
            border_color="#CFC8C0"
        )
        
        # 替換掉原本的 FilePicker 按鈕區域
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
                    on_click=self.on_paste_import
                ),
                ft.Container(height=20),
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Container(width=4, height=4, bgcolor=COLOR_PRIMARY, border_radius=2), ft.Text("注意事項", size=12, color=COLOR_PRIMARY)]),
                        ft.Text("僅讀取前 5 欄：代碼、分類、類別、品名、規格\n系統過濾 'ZZ' 或 '待' 開頭項目", size=12, color=COLOR_TEXT_SUB)
                    ]),
                    bgcolor="#F5F2EF", padding=15, border_radius=5
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=30,
            border=ft.border.all(1, "#CFC8C0"),
            border_radius=10,
            bgcolor="#FAF9F7",
        )
        
        # 更新 admin_view 內容
        self.admin_view.controls[5] = upload_area

    def on_paste_import(self, e):
        content = self.csv_input.value
        if not content:
            self.show_snack("請先貼上內容", False)
            return
        self.process_csv_content(content)
        self.csv_input.value = "" # 清空
        self.switch_tab("search")

# -----------------------------------------------------------------------------
# 啟動
# -----------------------------------------------------------------------------
def main(page: ft.Page):
    app = ImprovedProductApp(page)

if __name__ == "__main__":
    # 這裡的 view=ft.AppView.WEB_BROWSER 會在瀏覽器開啟
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)