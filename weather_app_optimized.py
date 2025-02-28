import sys
import time
import json
import os
import requests
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QLineEdit, QPushButton, QTabWidget, QGridLayout,
                            QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QCompleter,
                            QMessageBox, QSplashScreen, QProgressBar, QStatusBar)
from PyQt5.QtCore import Qt, QDateTime, QStringListModel, QSize, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap

# API配置
API_KEY = "yourapikey"
CITY_SEARCH_URL = "https://geoapi.qweather.com/v2/city/lookup"
WEATHER_URL = "https://devapi.qweather.com/v7/weather/now"
FORECAST_URL = "https://devapi.qweather.com/v7/weather/3d"
INDEX_URL = "https://devapi.qweather.com/v7/indices/1d"

# 缓存配置
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_EXPIRY = 30 * 60  # 缓存过期时间（秒）

# 天气图标映射
WEATHER_ICONS = {
    "晴": "sunny.png",
    "多云": "cloudy.png",
    "阴": "overcast.png",
    "小雨": "light_rain.png",
    "中雨": "moderate_rain.png",
    "大雨": "heavy_rain.png",
    "暴雨": "storm.png",
    "雷阵雨": "thunderstorm.png",
    "小雪": "light_snow.png",
    "中雪": "moderate_snow.png",
    "大雪": "heavy_snow.png",
    "暴雪": "snowstorm.png",
    "雾": "fog.png",
    "霾": "haze.png"
}

# 生活指数类型
LIFE_INDICES = {
    "1": "运动指数",
    "2": "洗车指数",
    "3": "穿衣指数",
    "5": "紫外线指数",
    "9": "感冒指数",
    "13": "舒适度指数"
}

# 确保缓存目录存在
def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

# 缓存管理
class CacheManager:
    @staticmethod
    def get_cache_path(key, cache_type):
        return os.path.join(CACHE_DIR, f"{cache_type}_{key}.json")
    
    @staticmethod
    def save_to_cache(key, data, cache_type):
        ensure_cache_dir()
        cache_path = CacheManager.get_cache_path(key, cache_type)
        cache_data = {
            "timestamp": time.time(),
            "data": data
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
    
    @staticmethod
    def get_from_cache(key, cache_type):
        cache_path = CacheManager.get_cache_path(key, cache_type)
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            
            # 检查缓存是否过期
            if time.time() - cache_data["timestamp"] > CACHE_EXPIRY:
                return None
            
            return cache_data["data"]
        except Exception:
            return None

# API请求函数
def get_city_id(city_name, timeout=5, max_retries=3):
    # 检查缓存
    cache_key = city_name
    cached_data = CacheManager.get_from_cache(cache_key, "city")
    if cached_data:
        return cached_data["id"], cached_data["name"]
    
    # 发起API请求
    params = {"location": city_name, "key": API_KEY}
    for retry in range(max_retries):
        try:
            response = requests.get(CITY_SEARCH_URL, params=params, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                if data["code"] == "200" and data["location"]:
                    result = {"id": data["location"][0]["id"], "name": data["location"][0]["name"]}
                    # 保存到缓存
                    CacheManager.save_to_cache(cache_key, result, "city")
                    return result["id"], result["name"]
                else:
                    return None, f"城市搜索失败: {data.get('message', '未知错误')}"
        except requests.Timeout:
            if retry == max_retries - 1:
                return None, "请求超时，请检查网络连接"
        except requests.RequestException as e:
            if retry == max_retries - 1:
                return None, f"网络请求异常: {str(e)}"
        if retry < max_retries - 1:
            time.sleep(1)  # 重试前等待1秒
    return None, "请求失败，请稍后重试"

def get_life_index(city_id, index_type="5", timeout=5, max_retries=3):
    # 检查缓存
    cache_key = f"{city_id}_{index_type}"
    cached_data = CacheManager.get_from_cache(cache_key, "index")
    if cached_data:
        return cached_data["level"], cached_data["category"]
    
    # 发起API请求
    params = {
        "location": city_id,
        "key": API_KEY,
        "type": index_type,
        "lang": "zh"
    }
    for retry in range(max_retries):
        try:
            response = requests.get(INDEX_URL, params=params, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                if data["code"] == "200":
                    result = {"level": data["daily"][0]["level"], "category": data["daily"][0]["category"]}
                    # 保存到缓存
                    CacheManager.save_to_cache(cache_key, result, "index")
                    return result["level"], result["category"]
        except requests.Timeout:
            if retry == max_retries - 1:
                return "未知", "请求超时"
        except requests.RequestException:
            if retry == max_retries - 1:
                return "未知", "网络异常"
        if retry < max_retries - 1:
            time.sleep(1)  # 重试前等待1秒
    return "未知", "未知"

def get_all_life_indices(city_id):
    indices = {}
    for index_id, index_name in LIFE_INDICES.items():
        level, category = get_life_index(city_id, index_type=index_id)
        indices[index_name] = {"level": level, "category": category}
    return indices

def get_weather(city_id, timeout=5, max_retries=3):
    # 检查缓存
    cache_key = city_id
    cached_data = CacheManager.get_from_cache(cache_key, "weather")
    if cached_data:
        return cached_data, None
    
    # 发起API请求
    params = {"location": city_id, "key": API_KEY, "lang": "zh", "unit": "m"}
    for retry in range(max_retries):
        try:
            response = requests.get(WEATHER_URL, params=params, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                if data["code"] == "200":
                    # 保存到缓存
                    CacheManager.save_to_cache(cache_key, data["now"], "weather")
                    return data["now"], None
                else:
                    return None, f"错误: {data['code']} - {data['message']}"
        except requests.Timeout:
            if retry == max_retries - 1:
                return None, "请求超时，请检查网络连接"
        except requests.RequestException as e:
            if retry == max_retries - 1:
                return None, f"网络请求异常: {str(e)}"
        if retry < max_retries - 1:
            time.sleep(1)  # 重试前等待1秒
    return None, "请求失败，请稍后重试"

def get_3day_forecast(city_id, timeout=5, max_retries=3):
    # 检查缓存
    cache_key = city_id
    cached_data = CacheManager.get_from_cache(cache_key, "forecast")
    if cached_data:
        return cached_data, None
    
    # 发起API请求
    params = {"location": city_id, "key": API_KEY, "lang": "zh", "unit": "m"}
    for retry in range(max_retries):
        try:
            response = requests.get(FORECAST_URL, params=params, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                if data["code"] == "200":
                    # 保存到缓存
                    CacheManager.save_to_cache(cache_key, data["daily"], "forecast")
                    return data["daily"], None
                else:
                    return None, f"错误: {data['code']} - {data['message']}"
        except requests.Timeout:
            if retry == max_retries - 1:
                return None, "请求超时，请检查网络连接"
        except requests.RequestException as e:
            if retry == max_retries - 1:
                return None, f"网络请求异常: {str(e)}"
        if retry < max_retries - 1:
            time.sleep(1)  # 重试前等待1秒
    return None, "请求失败，请稍后重试"

# 获取天气图标
def get_weather_icon(weather_text):
    # 尝试精确匹配
    if weather_text in WEATHER_ICONS:
        return WEATHER_ICONS[weather_text]
    
    # 尝试模糊匹配
    for key in WEATHER_ICONS:
        if key in weather_text:
            return WEATHER_ICONS[key]
    
    # 默认图标
    return "unknown.png"

# 主应用类
class WeatherApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("天气查询应用")
        self.setMinimumSize(900, 700)
        
        # 历史记录列表
        self.history = []
        self.max_history = 10
        
        # 当前城市ID
        self.current_city_id = None
        self.current_city_name = None
        
        # 自动刷新定时器
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_weather)
        
        # 主窗口部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 主布局
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # 搜索区域
        self.setup_search_area()
        
        # 设置自动补全
        self.setup_autocomplete()
        
        # 标签页
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        # 当前天气标签页
        self.setup_current_weather_tab()
        
        # 预报标签页
        self.setup_forecast_tab()
        
        # 生活指数标签页
        self.setup_life_index_tab()
        
        # 状态栏
        self.statusBar().showMessage("准备就绪")
        
        # 应用样式
        self.apply_styles()
        
        # 创建缓存目录
        ensure_cache_dir()
        
        # 尝试加载上次查询的城市
        self.load_last_city()

    def setup_search_area(self):
        search_layout = QHBoxLayout()
        
        # 城市输入
        self.city_label = QLabel("城市名称:")
        self.city_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("请输入城市名称（如北京）")
        self.city_input.returnPressed.connect(self.search_weather)
        
        # 搜索按钮
        self.search_button = QPushButton("查询天气")
        self.search_button.clicked.connect(self.search_weather)
        
        # 刷新按钮
        self.refresh_button = QPushButton("刷新数据")
        self.refresh_button.clicked.connect(self.refresh_weather)
        
        # 添加到布局
        search_layout.addWidget(self.city_label)
        search_layout.addWidget(self.city_input, 1)  # 1是伸展因子，让输入框占据更多空间
        search_layout.addWidget(self.search_button)
        search_layout.addWidget(self.refresh_button)
        
        # 添加到主布局
        self.main_layout.addLayout(search_layout)
        
        # 添加分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        self.main_layout.addWidget(line)
    
    def setup_autocomplete(self):
        # 创建自动补全器
        self.completer = QCompleter()
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.city_input.setCompleter(self.completer)
        
        # 设置自动补全数据模型
        self.completer_model = QStringListModel()
        self.completer.setModel(self.completer_model)
        self.update_completer_model()
    
    def update_completer_model(self):
        # 更新自动补全数据
        self.completer_model.setStringList(self.history)
    
    def setup_current_weather_tab(self):
        self.current_weather_tab = QWidget()
        self.tabs.addTab(self.current_weather_tab, "实时天气")
        self.current_weather_layout = QVBoxLayout(self.current_weather_tab)
        
        # 天气信息表格
        self.weather_table = QTableWidget()
        self.weather_table.setColumnCount(2)
        self.weather_table.setHorizontalHeaderLabels(["项目", "值"])
        self.weather_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.current_weather_layout.addWidget(self.weather_table)
        
        # 天气图标显示区域
        self.weather_icon_layout = QHBoxLayout()
        self.weather_icon_label = QLabel()
        self.weather_icon_label.setAlignment(Qt.AlignCenter)
        self.weather_icon_layout.addWidget(self.weather_icon_label)
        self.current_weather_layout.addLayout(self.weather_icon_layout)
    
    def setup_forecast_tab(self):
        self.forecast_tab = QWidget()
        self.tabs.addTab(self.forecast_tab, "未来3天预报")
        self.forecast_layout = QVBoxLayout(self.forecast_tab)
        
        # 预报表格
        self.forecast_table = QTableWidget()
        self.forecast_table.setColumnCount(5)
        self.forecast_table.setHorizontalHeaderLabels(["日期", "白天天气", "夜间天气", "温度范围", "风速"])
        self.forecast_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.forecast_layout.addWidget(self.forecast_table)
    
    def setup_life_index_tab(self):
        self.life_index_tab = QWidget()
        self.tabs.addTab(self.life_index_tab, "生活指数")
        self.life_index_layout = QVBoxLayout(self.life_index_tab)
        
        # 生活指数表格
        self.life_index_table = QTableWidget()
        self.life_index_table.setColumnCount(3)
        self.life_index_table.setHorizontalHeaderLabels(["指数类型", "等级", "建议"])
        self.life_index_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.life_index_layout.addWidget(self.life_index_table)
    
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QTableWidget {
                background-color: white;
                border-radius: 5px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QLineEdit {
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #ccc;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom-color: white;
            }
        """)
    
    def add_to_history(self, city_name):
        # 添加到历史记录
        if city_name in self.history:
            self.history.remove(city_name)
        self.history.insert(0, city_name)
        
        # 保持历史记录在最大限制内
        if len(self.history) > self.max_history:
            self.history = self.history[:self.max_history]
        
        # 更新自动补全
        self.update_completer_model()
        
        # 保存历史记录到文件
        self.save_history()
    
    def save_history(self):
        # 保存历史记录到文件
        history_path = os.path.join(CACHE_DIR, "history.json")
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump({"history": self.history}, f, ensure_ascii=False)
        except Exception:
            pass
    
    def load_history(self):
        # 从文件加载历史记录
        history_path = os.path.join(CACHE_DIR, "history.json")
        if os.path.exists(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.history = data.get("history", [])
                    self.update_completer_model()
            except Exception:
                pass
    
    def save_last_city(self):
        # 保存最后查询的城市
        if self.current_city_id and self.current_city_name:
            last_city_path = os.path.join(CACHE_DIR, "last_city.json")
            try:
                with open(last_city_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "id": self.current_city_id,
                        "name": self.current_city_name
                    }, f, ensure_ascii=False)
            except Exception:
                pass
    
    def load_last_city(self):
        # 加载历史记录
        self.load_history()
        
        # 加载最后查询的城市
        last_city_path = os.path.join(CACHE_DIR, "last_city.json")
        if os.path.exists(last_city_path):
            try:
                with open(last_city_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    city_id = data.get("id")
                    city_name = data.get("name")
                    if city_id and city_name:
                        self.current_city_id = city_id
                        self.current_city_name = city_name
                        self.city_input.setText(city_name)
                        self.refresh_weather()
            except Exception:
                pass
    
    def search_weather(self):
        city_name = self.city_input.text().strip()
        if not city_name:
            self.statusBar().showMessage("请输入城市名称")
            return
        
        self.statusBar().showMessage(f"正在查询 {city_name} 的天气...")
        
        # 获取城市ID
        city_id, city_name = get_city_id(city_name)
        if not city_id:
            self.statusBar().showMessage(city_name)  # 错误信息
            return
        
        # 保存当前城市信息
        self.current_city_id = city_id
        self.current_city_name = city_name
        
        # 添加到历史记录
        self.add_to_history(city_name)
        
        # 保存最后查询的城市
        self.save_last_city()
        
        # 更新窗口标题
        self.setWindowTitle(f"天气查询应用 - {city_name}")
        
        # 获取并显示天气数据
        self.update_all_weather_data()
    
    def refresh_weather(self):
        if not self.current_city_id:
            return
        
        self.statusBar().showMessage(f"正在刷新 {self.current_city_name} 的天气数据...")
        self.update_all_weather_data()
    
    def update_all_weather_data(self):
        # 获取并显示当前天气
        self.update_current_weather()
        
        # 获取并显示天气预报
        self.update_forecast()
        
        # 获取并显示生活指数
        self.update_life_indices()
        
        # 更新状态栏
        self.statusBar().showMessage(
            f"{self.current_city_name} 天气数据已更新 - {QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')}"
        )
    
    def update_current_weather(self):
        weather_data, error = get_weather(self.current_city_id)
        if error:
            self.statusBar().showMessage(error)
            return
        
        # 获取紫外线指数
        uv_level, uv_category = get_life_index(self.current_city_id, index_type="5")
        
        # 清空表格
        self.weather_table.setRowCount(0)
        
        # 添加天气数据
        weather_items = [
            ["天气状况", weather_data["text"]],
            ["温度", f"{weather_data['temp']}°C（体感 {weather_data['feelsLike']}°C）"],
            ["湿度", f"{weather_data['humidity']}%"],
            ["风向风力", f"{weather_data['windDir']} {weather_data['windScale']}级"],
            ["风速", f"{weather_data['windSpeed']} 米/秒"],
            ["气压", f"{weather_data['pressure']} 百帕"],
            ["降水量", f"{weather_data['precip']} 毫米"],
            ["能见度", f"{weather_data['vis']} 公里"],
            ["云量", f"{weather_data.get('cloud', '未知')}%"],
            ["紫外线指数", f"{uv_level} ({uv_category})"],
            ["观测时间", weather_data["obsTime"]]
        ]
        
        self.weather_table.setRowCount(len(weather_items))
        
        for row, (item, value) in enumerate(weather_items):
            self.weather_table.setItem(row, 0, QTableWidgetItem(item))
            self.weather_table.setItem(row, 1, QTableWidgetItem(value))
        
        # 尝试显示天气图标
        try:
            icon_name = get_weather_icon(weather_data["text"])
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", icon_name)
            if os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
                self.weather_icon_label.setPixmap(pixmap.scaled(QSize(64, 64), Qt.KeepAspectRatio))
            else:
                self.weather_icon_label.setText(f"天气: {weather_data['text']}")
        except Exception:
            self.weather_icon_label.setText(f"天气: {weather_data['text']}")
    
    def update_forecast(self):
        forecast_data, error = get_3day_forecast(self.current_city_id)
        if error:
            self.statusBar().showMessage(error)
            return
        
        # 清空表格
        self.forecast_table.setRowCount(0)
        
        # 添加预报数据
        self.forecast_table.setRowCount(len(forecast_data))
        
        for row, day in enumerate(forecast_data):
            date_item = QTableWidgetItem(day["fxDate"])
            day_weather = QTableWidgetItem(day["textDay"])
            night_weather = QTableWidgetItem(day["textNight"])
            temp_range = QTableWidgetItem(f"{day['tempMin']}°C ~ {day['tempMax']}°C")
            wind_speed = QTableWidgetItem(f"{day['windDirDay']} {day['windScaleDay']}级 ({day['windSpeedDay']}米/秒)")
            
            self.forecast_table.setItem(row, 0, date_item)
            self.forecast_table.setItem(row, 1, day_weather)
            self.forecast_table.setItem(row, 2, night_weather)
            self.forecast_table.setItem(row, 3, temp_range)
            self.forecast_table.setItem(row, 4, wind_speed)
    
    def update_life_indices(self):
        # 获取所有生活指数
        indices = get_all_life_indices(self.current_city_id)
        
        # 清空表格
        self.life_index_table.setRowCount(0)
        
        # 添加生活指数数据
        self.life_index_table.setRowCount(len(indices))
        
        for row, (index_name, data) in enumerate(indices.items()):
            index_item = QTableWidgetItem(index_name)
            level_item = QTableWidgetItem(data["level"])
            category_item = QTableWidgetItem(data["category"])
            
            self.life_index_table.setItem(row, 0, index_item)
            self.life_index_table.setItem(row, 1, level_item)
            self.life_index_table.setItem(row, 2, category_item)


if __name__ == "__main__":
    # 创建应用
    app = QApplication(sys.argv)
    
    # 创建启动画面
    splash_pix = QPixmap(200, 200)
    splash_pix.fill(Qt.white)
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()
    
    # 显示启动信息
    splash.showMessage("正在加载天气查询应用...", Qt.AlignCenter | Qt.AlignBottom, Qt.black)
    
    # 创建主窗口
    window = WeatherApp()
    
    # 关闭启动画面，显示主窗口
    splash.finish(window)
    window.show()
    
    # 运行应用
    sys.exit(app.exec_())
