import os
import sys
import shutil
from pathlib import Path
import ctypes
from datetime import datetime, timedelta
import logging
import customtkinter as ctk
from tkinter import messagebox, filedialog, END
import threading
import queue
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import functools
import win32file
import win32con
import pywintypes
import win32api
from ai_assistant import AIAssistant

def timeout(seconds, error_message="操作超时"):
    """超时装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = queue.Queue()
            
            def worker():
                try:
                    result.put(("success", func(*args, **kwargs)))
                except Exception as e:
                    result.put(("error", e))
            
            thread = threading.Thread(target=worker)
            thread.daemon = True
            thread.start()
            
            try:
                status, value = result.get(timeout=seconds)
                if status == "error":
                    raise value
                return value
            except queue.Empty:
                raise TimeoutError(error_message)
            
        return wrapper
    return decorator

class LogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        log_message = self.format(record)
        self.callback(log_message + "\n")

class PowerShellTerminal(ctk.CTkTextbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configure(font=("Consolas", 12))
        self.tag_config("prompt", foreground="lightgreen")
        self.tag_config("output", foreground="white")
        self.tag_config("error", foreground="red")
        
        # 初始化状态
        self.process = None
        self.running = False
        self.command_history = []
        self.history_index = 0
        self.current_command = ""
        self.command_start = "1.0"
        
        try:
            # 使用更少的内存启动PowerShell
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            self.process = subprocess.Popen(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # 启动读取线程
            self.running = True
            self.output_thread = threading.Thread(target=self._read_output, daemon=True)
            self.error_thread = threading.Thread(target=self._read_error, daemon=True)
            self.output_thread.start()
            self.error_thread.start()
            
            # 绑定按键事件
            self.bind("<Return>", self._on_enter)
            self.bind("<Key>", self._on_key)
            
            # 显示初始提示符
            self.show_prompt()
            
        except Exception as e:
            self.insert(END, f"PowerShell启动失败: {str(e)}\n", "error")
            self.insert(END, "终端将以只读模式运行\n", "error")
            logging.error(f"PowerShell启动失败: {str(e)}")
    
    def show_prompt(self):
        """显示PowerShell提示符"""
        try:
            current_dir = os.getcwd()
            self.insert(END, f"PS {current_dir}> ", "prompt")
            self.command_start = self.index("end-1c")
            self.see(END)
        except Exception as e:
            self.insert(END, "PS > ", "prompt")
            self.command_start = self.index("end-1c")
            self.see(END)
    
    def _on_key(self, event):
        """处理按键事件"""
        if not self.process:  # 如果PowerShell未启动，禁用输入
            return "break"
            
        if event.keysym in ['Up', 'Down']:
            return self._handle_history(event.keysym)
        elif event.keysym in ['Left', 'BackSpace']:
            # 防止删除提示符
            if self.index("insert") <= self.command_start:
                return "break"
        return None
    
    def _on_enter(self, event):
        """处理回车事件"""
        if not self.process:  # 如果PowerShell未启动，禁用输入
            return "break"
            
        command = self.get(self.command_start, "end-1c")
        if command:
            self.command_history.append(command)
            self.history_index = len(self.command_history)
            
        self.insert(END, "\n")
        if command.strip():
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except Exception as e:
                self.insert(END, str(e) + "\n", "error")
                self.show_prompt()
        else:
            self.show_prompt()
            
        return "break"
    
    def _read_output(self):
        """读取PowerShell输出"""
        while self.running and self.process:
            try:
                line = self.process.stdout.readline()
                if line:
                    self.insert(END, line, "output")
                    self.see(END)
                    if not line.endswith("\n"):
                        self.insert(END, "\n")
                    if "PS " not in line:  # 避免重复显示提示符
                        self.show_prompt()
            except Exception:
                if self.running:
                    time.sleep(0.1)
    
    def _read_error(self):
        """读取PowerShell错误输出"""
        while self.running and self.process:
            try:
                line = self.process.stderr.readline()
                if line:
                    self.insert(END, line, "error")
                    self.see(END)
            except Exception:
                if self.running:
                    time.sleep(0.1)
    
    def destroy(self):
        """清理资源"""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
        super().destroy()

class DiskCleaner(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # 初始化基本属性
        self.scanning = False
        self.scan_start_time = None
        self.processed_files = 0
        self.total_files = 0
        self.skipped_files = 0
        self.total_space_cleared = 0
        self.cleanable_files = []
        self.system_dirs = {
            'Windows', 
            'Program Files', 
            'Program Files (x86)', 
            'ProgramData',
            'System32',
            'System Volume Information'
        }
        
        # 初始化AI助手
        self.ai_assistant = None
        try:
            # 尝试初始化AI助手，不再需要检查环境变量
            self.ai_assistant = AIAssistant()
        except Exception as e:
            logging.error(f"初始化AI助手失败: {e}")
        
        # 设置窗口属性
        self.title("磁盘清理助手")
        self.geometry("1200x800")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 设置网格权重
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # 创建消息队列和UI更新批处理列表
        self._update_queue = queue.Queue()
        self.ui_update_batch = []
        self.last_ui_update = time.time()
        
        # 设置日志
        self.setup_logging()
        
        # 创建UI组件
        self.create_widgets()
        
        # 更新驱动器信息
        self.update_drive_info()
        
        # 检查消息队列
        self.check_queue()

    @property
    def update_queue(self):
        return self._update_queue

    def check_queue(self):
        """检查队列中的UI更新请求"""
        try:
            while True:
                update = self._update_queue.get_nowait()
                update_type = update.get('type')
                
                if update_type == 'progress':
                    self.progress_bar.set(update['value'])
                elif update_type == 'status':
                    self.status_label.configure(text=update['text'])
                elif update_type == 'result':
                    self.result_text.insert("end", update['text'])
                    self.result_text.see("end")
                elif update_type == 'log':
                    self.log_text.insert("end", update['text'])
                    self.log_text.see("end")
                elif update_type == 'buttons':
                    if 'scan' in update:
                        self.scan_button.configure(state=update['scan'])
                    if 'clean' in update:
                        self.clean_button.configure(state=update['clean'])
                
                self._update_queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.after(100, self.check_queue)

    def on_closing(self):
        """处理窗口关闭事件"""
        if self.scanning:
            if messagebox.askokcancel("确认", "正在扫描中，确定要退出吗？"):
                self.scanning = False
                self.destroy()
        else:
            self.destroy()

    def update_scan_status(self):
        """更新扫描状态"""
        if not self.scanning or not self.scan_start_time:
            return
            
        current_time = time.time()
        # 每0.5秒更新一次UI
        if current_time - self.last_ui_update < 0.5:
            return
            
        self.last_ui_update = current_time
        elapsed_time = int(current_time - self.scan_start_time)
        
        # 计算扫描速度
        if elapsed_time > 0:
            files_per_second = self.processed_files / elapsed_time
            remaining_files = self.total_files - self.processed_files
            estimated_remaining = int(remaining_files / files_per_second) if files_per_second > 0 else 0
        else:
            estimated_remaining = 0
            
        # 更新状态信息
        status_text = (
            f"正在扫描: {self.processed_files}/{self.total_files} "
            f"已跳过: {self.skipped_files} "
            f"已用时: {elapsed_time}秒 "
            f"预计剩余: {estimated_remaining}秒"
        )
        
        self.update_ui(type='status', text=status_text)
        progress = self.processed_files / self.total_files if self.total_files > 0 else 0
        self.update_ui(type='progress', value=progress)

    @timeout(5, "获取文件信息超时")
    def get_file_info_with_timeout(self, path):
        try:
            stats = os.stat(path)
            return {
                'size': stats.st_size,
                'last_accessed': datetime.fromtimestamp(stats.st_atime)
            }
        except (PermissionError, FileNotFoundError):
            return None
                    
    def process_file(self, file_path, days_old):
        """处理单个文件"""
        try:
            file_info = self.get_file_info_with_timeout(file_path)
            if file_info and (datetime.now() - file_info['last_accessed']).days > days_old:
                return {
                    'path': file_path,
                    'size': file_info['size'],
                    'last_accessed': file_info['last_accessed']
                }
        except Exception as e:
            self.skipped_files += 1
            logging.warning(f"处理文件失败 {file_path}: {str(e)}")
        return None

    def scan_directory(self, directory):
        """扫描目录并返回可以清理的文件"""
        self.cleanable_files = []
        self.scanning = True
        self.scan_start_time = time.time()
        self.processed_files = 0
        self.total_files = 0
        self.skipped_files = 0
        self.last_ui_update = 0

        try:
            days_old = int(self.days_entry.get())
        except ValueError:
            self.update_ui(type='status', text="错误：请输入有效的天数")
            return []

        if not os.path.exists(directory):
            self.update_ui(type='status', text="错误：目录不存在")
            return []

        try:
            # 快速统计文件数量
            self.update_ui(type='status', text="正在统计文件数量...")
            for root, _, files in os.walk(directory):
                if not self.scanning:
                    return []
                if not self.is_system_directory(root):
                    self.total_files += len(files)

            if self.total_files == 0:
                self.update_ui(type='status', text="未找到任何文件")
                return []

            # 创建文件队列
            file_queue = queue.Queue()
            
            # 生产者线程：收集文件
            def collect_files():
                try:
                    for root, _, files in os.walk(directory):
                        if not self.scanning:
                            return
                        if self.is_system_directory(root):
                            continue
                        for file in files:
                            if not self.scanning:
                                return
                            file_queue.put(os.path.join(root, file))
                finally:
                    file_queue.put(None)  # 结束标记

            # 消费者线程：处理文件
            def process_files():
                while self.scanning:
                    try:
                        file_path = file_queue.get(timeout=1)
                        if file_path is None:
                            break
                            
                        result = self.process_file(file_path, days_old)
                        if result:
                            self.cleanable_files.append(result)
                            
                        self.processed_files += 1
                        self.update_scan_status()
                        
                    except queue.Empty:
                        continue
                    except Exception as e:
                        logging.error(f"处理文件出错: {str(e)}")
                        self.skipped_files += 1

            # 启动生产者线程
            collector = threading.Thread(target=collect_files)
            collector.start()

            # 启动消费者线程
            processor = threading.Thread(target=process_files)
            processor.start()

            # 等待线程完成
            collector.join()
            processor.join()

        except Exception as e:
            error_msg = f"扫描目录时出错: {str(e)}"
            logging.error(error_msg)
            self.update_ui(type='status', text=error_msg)
            messagebox.showerror("错误", error_msg)

        self.scanning = False
        
        # 显示最终状态
        final_status = (
            f"扫描完成！处理文件: {self.processed_files} "
            f"跳过: {self.skipped_files} "
            f"用时: {int(time.time() - self.scan_start_time)}秒"
        )
        self.update_ui(type='status', text=final_status)
        
        return self.cleanable_files

    def start_scan(self):
        directory = self.dir_entry.get()
        if not directory:
            messagebox.showerror("错误", "请输入要扫描的目录")
            return

        if self.scanning:
            if messagebox.askyesno("确认", "正在扫描中，是否停止当前扫描？"):
                self.scanning = False
                return
            else:
                return

        # 清空结果显示
        self.result_text.delete("1.0", "end")
        
        # 重置进度条和按钮状态
        self.update_ui(type='progress', value=0)
        self.update_ui(type='buttons', scan='disabled', clean='disabled')

        def scan_thread():
            try:
                files = self.scan_directory(directory)
                
                if not files:
                    self.update_ui(type='status', text="未找到可清理的文件")
                    self.update_ui(type='buttons', scan='normal')
                    return

                total_size = sum(f['size'] for f in files)
                
                # 更新结果显示
                self.update_ui(type='result', text=f"扫描完成！\n")
                self.update_ui(type='result', text=f"找到 {len(files)} 个可清理的文件\n")
                self.update_ui(type='result', text=f"总计可释放空间: {self.format_size(total_size)}\n\n")
                
                # 分批显示文件
                for i, file in enumerate(files[:100]):
                    if i % 10 == 0:  # 每10个文件更新一次显示
                        time.sleep(0.1)  # 短暂暂停，让UI有时间更新
                    self.update_ui(type='result', text=f"文件: {file['path']}\n")
                    self.update_ui(type='result', text=f"大小: {self.format_size(file['size'])}\n")
                    self.update_ui(type='result', text=f"最后访问: {file['last_accessed']}\n\n")

                if len(files) > 100:
                    self.update_ui(type='result', text="...(仅显示前100个文件)\n")

                # 更新按钮状态和进度显示
                self.update_ui(type='buttons', scan='normal', clean='normal')
                self.update_ui(type='progress', value=1)
                
            except Exception as e:
                error_msg = f"扫描过程出错: {str(e)}"
                logging.error(error_msg)
                self.update_ui(type='status', text=error_msg)
                messagebox.showerror("错误", error_msg)
                self.update_ui(type='buttons', scan='normal')

        # 启动扫描线程
        threading.Thread(target=scan_thread, daemon=True).start()

    def setup_logging(self):
        """设置日志处理"""
        # 清除现有的处理器
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
            
        # 设置根日志记录器
        logging.root.setLevel(logging.INFO)
        
        # 添加定义处理器
        handler = LogHandler(self.log_message)
        logging.root.addHandler(handler)

    def log_message(self, message):
        """添加日志消息到日志显示区域"""
        self.update_ui(type='log', text=message)

    def create_widgets(self):
        # 创建主框架
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=5)
        
        # 创建左侧面板
        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        
        # 添加AI助手聊天框
        self.create_ai_chat_widgets()
        
        # 左侧控制面板
        self.control_frame = ctk.CTkFrame(self.main_frame)
        self.control_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 上半部分：清理工具控制区
        self.tool_frame = ctk.CTkFrame(self.control_frame)
        self.tool_frame.pack(fill="x", padx=10, pady=5)

        # 标题
        self.title_label = ctk.CTkLabel(
            self.tool_frame, 
            text="磁盘清理工具", 
            font=("Arial", 24, "bold")
        )
        self.title_label.pack(pady=10)

        # 磁盘选择框架
        self.drives_frame = ctk.CTkFrame(self.tool_frame)
        self.drives_frame.pack(fill="x", padx=10, pady=5)

        self.drives_label = ctk.CTkLabel(self.drives_frame, text="选择磁盘：")
        self.drives_label.pack(side="left", padx=5)

        # 获取磁盘列表
        self.drives = self.get_drives()
        self.drive_var = ctk.StringVar(value="C:\\")
        
        # 创建磁盘选择下拉菜单
        self.drive_menu = ctk.CTkOptionMenu(
            self.drives_frame,
            values=[drive['letter'] for drive in self.drives],
            variable=self.drive_var,
            width=100
        )
        self.drive_menu.pack(side="left", padx=5)

        # 显示选中磁盘信息
        self.drive_info_label = ctk.CTkLabel(self.drives_frame, text="")
        self.drive_info_label.pack(side="left", padx=5)
        
        # 更新磁盘信息显示
        self.update_drive_info()

        # 目录选择框架
        self.dir_frame = ctk.CTkFrame(self.tool_frame)
        self.dir_frame.pack(fill="x", padx=10, pady=5)

        self.dir_label = ctk.CTkLabel(self.dir_frame, text="目标目录：")
        self.dir_label.pack(side="left", padx=5)

        self.dir_entry = ctk.CTkEntry(self.dir_frame, width=200)
        self.dir_entry.pack(side="left", padx=5)
        self.dir_entry.insert(0, self.drive_var.get())

        self.browse_button = ctk.CTkButton(
            self.dir_frame, 
            text="浏览", 
            command=self.browse_directory
        )
        self.browse_button.pack(side="left", padx=5)

        # 绑定磁盘选择变更事件
        self.drive_var.trace('w', lambda *args: self.on_drive_change())

        # 天数选择
        self.days_frame = ctk.CTkFrame(self.tool_frame)
        self.days_frame.pack(fill="x", padx=10, pady=5)

        self.days_label = ctk.CTkLabel(self.days_frame, text="清理超过多少天未访问的文件：")
        self.days_label.pack(side="left", padx=5)

        self.days_entry = ctk.CTkEntry(self.days_frame, width=100)
        self.days_entry.pack(side="left", padx=5)
        self.days_entry.insert(0, "30")

        # 进度显示
        self.progress_frame = ctk.CTkFrame(self.tool_frame)
        self.progress_frame.pack(fill="x", padx=10, pady=5)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.pack(fill="x", padx=5, pady=5)
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(self.progress_frame, text="准备就绪")
        self.status_label.pack(pady=5)

        # 操作按钮
        self.button_frame = ctk.CTkFrame(self.tool_frame)
        self.button_frame.pack(fill="x", padx=10, pady=5)

        self.scan_button = ctk.CTkButton(
            self.button_frame, 
            text="扫描", 
            command=self.start_scan
        )
        self.scan_button.pack(side="left", padx=5)

        self.clean_button = ctk.CTkButton(
            self.button_frame, 
            text="清理", 
            command=self.start_clean,
            state="disabled"
        )
        self.clean_button.pack(side="left", padx=5)

        # 下半部分：PowerShell终端
        self.terminal_frame = ctk.CTkFrame(self.control_frame)
        self.terminal_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.terminal_label = ctk.CTkLabel(
            self.terminal_frame,
            text="PowerShell终端",
            font=("Arial", 16, "bold")
        )
        self.terminal_label.pack(pady=5)

        try:
            self.terminal = PowerShellTerminal(
                self.terminal_frame,
                height=300,
                wrap="none"
            )
            self.terminal.pack(fill="both", expand=True, padx=5, pady=5)
        except Exception as e:
            # 如果PowerShell终端创建失败，显示错误信息
            self.terminal = ctk.CTkTextbox(
                self.terminal_frame,
                height=300,
                wrap="none"
            )
            self.terminal.pack(fill="both", expand=True, padx=5, pady=5)
            self.terminal.insert(END, "PowerShell终端初始化失败\n")
            self.terminal.insert(END, f"错误: {str(e)}\n")
            self.terminal.configure(state="disabled")
            logging.error(f"PowerShell终端初始化失败: {str(e)}")

        # 右侧显示面板
        self.display_frame = ctk.CTkFrame(self.main_frame)
        self.display_frame.pack(side="left", fill="both", expand=True)

        # 结果显示标签
        self.result_label = ctk.CTkLabel(
            self.display_frame,
            text="扫描结果",
            font=("Arial", 16, "bold")
        )
        self.result_label.pack(pady=5)

        # 结果显示区域
        self.result_text = ctk.CTkTextbox(self.display_frame, height=300)
        self.result_text.pack(fill="both", expand=True, padx=10, pady=5)

        # 日志显示标签
        self.log_label = ctk.CTkLabel(
            self.display_frame,
            text="运行日志",
            font=("Arial", 16, "bold")
        )
        self.log_label.pack(pady=5)

        # 日志显示区域
        self.log_text = ctk.CTkTextbox(self.display_frame, height=200)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

    def create_ai_chat_widgets(self):
        """创建AI助手聊天界面"""
        # 创建聊天框架
        self.chat_frame = ctk.CTkFrame(self.left_panel)
        self.chat_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.left_panel.grid_rowconfigure(0, weight=1)
        self.left_panel.grid_columnconfigure(0, weight=1)
        
        # 聊天显示区域
        self.chat_display = ctk.CTkTextbox(self.chat_frame, width=300, height=400)
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.chat_display.configure(state="disabled")
        
        # 输入框
        self.chat_input = ctk.CTkTextbox(self.chat_frame, width=300, height=100)
        self.chat_input.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        # 发送按钮
        self.send_button = ctk.CTkButton(
            self.chat_frame, 
            text="发送", 
            command=self.send_message
        )
        self.send_button.grid(row=2, column=0, sticky="e", padx=5, pady=5)
        
        # 配置网格
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)
        
        # 添加提示信息
        if not self.ai_assistant:
            self.chat_display.configure(state="normal")
            self.chat_display.insert(END, "请设置DEEPSEEK_API_KEY环境变量来启用AI助手功能。\n")
            self.chat_display.configure(state="disabled")
            self.chat_input.configure(state="disabled")
            self.send_button.configure(state="disabled")
        else:
            self.chat_display.configure(state="normal")
            self.chat_display.insert(END, "AI助手已准备就绪，请输入您的问题。\n")
            self.chat_display.configure(state="disabled")

    def send_message(self):
        """发送消息给AI助手"""
        if not self.ai_assistant:
            return
        
        message = self.chat_input.get("1.0", END).strip()
        if not message:
            return
            
        # 清空输入框
        self.chat_input.delete("1.0", END)
        
        # 显示用户消息
        self.chat_display.configure(state="normal")
        self.chat_display.insert(END, f"\n你: {message}\n")
        self.chat_display.configure(state="disabled")
        
        # 在新线程中获取AI响应
        def get_ai_response():
            try:
                response = self.ai_assistant.get_response(message)
                
                # 在主线程中更新UI
                self.after(0, lambda: self.update_chat_display(response))
            except Exception as e:
                error_message = f"获取AI响应时出错: {str(e)}"
                self.after(0, lambda: self.update_chat_display(error_message))
        
        threading.Thread(target=get_ai_response, daemon=True).start()
        
    def update_chat_display(self, message):
        """更新聊天显示区域"""
        self.chat_display.configure(state="normal")
        self.chat_display.insert(END, f"\nAI助手: {message}\n")
        self.chat_display.see(END)
        self.chat_display.configure(state="disabled")

    def destroy(self):
        """清理资源"""
        self.scanning = False
        if hasattr(self, 'thread_pool'):
            try:
                self.thread_pool.shutdown(wait=False)
            except Exception:
                pass
        if hasattr(self, 'terminal'):
            try:
                self.terminal.destroy()
            except Exception:
                pass
        super().destroy()

    def update_ui(self, **kwargs):
        """将UI更新请求添加到队列"""
        if not self.update_queue:  # 检查队列是否存在
            return
        try:
            # 如果是结果更新，先添加到批处理列表
            if kwargs.get('type') == 'result':
                self.ui_update_batch.append(kwargs)
                # 当批处理列表达到50个或距离上次更新超过0.5秒时，才实际更新UI
                if len(self.ui_update_batch) >= 50 or time.time() - self.last_ui_update >= 0.5:
                    combined_text = ''.join(item['text'] for item in self.ui_update_batch)
                    self.update_queue.put({'type': 'result', 'text': combined_text})
                    self.ui_update_batch = []
                    self.last_ui_update = time.time()
            else:
                self.update_queue.put(kwargs)
        except Exception as e:
            logging.error(f"UI更新错误: {str(e)}")

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, directory)

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def is_system_directory(self, path):
        """检查是否是系统目录"""
        parts = Path(path).parts
        return any(sys_dir in parts for sys_dir in self.system_dirs)

    def get_file_info(self, file_path):
        """获取文件信息"""
        try:
            stats = os.stat(file_path)
            return {
                'size': stats.st_size,
                'last_modified': datetime.fromtimestamp(stats.st_mtime),
                'last_accessed': datetime.fromtimestamp(stats.st_atime)
            }
        except Exception as e:
            logging.error(f"获取文件信息失败 {file_path}: {str(e)}")
            return None

    def format_size(self, size):
        """将字节转换为可读格式"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def process_directory(self, directory, days_old):
        """处理单个目录"""
        try:
            if self.is_system_directory(directory):
                return []
            
            files = []
            for entry in os.scandir(directory):
                if not self.scanning:  # 检查是否需要停止扫描
                    break
                    
                try:
                    if entry.is_file():
                        file_info = self.get_file_info(entry.path)
                        if file_info and (datetime.now() - file_info['last_accessed']).days > days_old:
                            files.append({
                                'path': entry.path,
                                'size': file_info['size'],
                                'last_accessed': file_info['last_accessed']
                            })
                    elif entry.is_dir():
                        try:
                            files.extend(self.process_directory(entry.path, days_old))
                        except PermissionError:
                            continue
                except Exception as e:
                    logging.error(f"处理文件出错 {entry.path}: {str(e)}")
                    continue
                    
            return files
        except Exception as e:
            logging.error(f"处理目录出错 {directory}: {str(e)}")
            return []

    def clean_files(self):
        """清理文件"""
        processed = 0
        total = len(self.cleanable_files)
        
        def force_delete_file(file_path):
            try:
                # 首先尝试常规删除
                os.remove(file_path)
                return True
            except PermissionError:
                try:
                    # 获取文件句柄
                    handle = win32file.CreateFile(
                        file_path,
                        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        0,  # 不共享
                        None,
                        win32file.OPEN_EXISTING,
                        win32file.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_DELETE_ON_CLOSE,
                        None
                    )
                    # 关闭句柄时会自动删除文件
                    win32file.CloseHandle(handle)
                    return True
                except pywintypes.error as e:
                    if e.winerror == 5:  # 访问被拒绝
                        try:
                            # 使用 Windows API 设置文件属性并强制删除
                            win32file.SetFileAttributes(file_path, win32con.FILE_ATTRIBUTE_NORMAL)
                            os.remove(file_path)
                            return True
                        except:
                            return False
                    return False
            except Exception:
                return False

        for file_info in self.cleanable_files:
            try:
                file_path = file_info['path']
                if os.path.exists(file_path) and not self.is_system_directory(file_path):
                    # 检查文件最后访问时间
                    stats = os.stat(file_path)
                    last_access = datetime.fromtimestamp(stats.st_atime)
                    days_unused = (datetime.now() - last_access).days
                    
                    if days_unused > int(self.days_entry.get()):
                        # 对非系统文件进行强制删除
                        if force_delete_file(file_path):
                            self.total_space_cleared += file_info['size']
                            self.update_ui(type='result', text=f"已删除: {file_path}\n")
                            logging.info(f"成功删除文件: {file_path}")
                        else:
                            error_msg = f"无法删除文件 {file_path}，即使在尝试强制删除后"
                            logging.error(error_msg)
                            self.update_ui(type='result', text=f"删除失败: {file_path}\n")
                    
                processed += 1
                progress = processed / total if total > 0 else 0
                self.update_ui(type='progress', value=progress)
                self.update_ui(type='status', text=f"正在清理: {processed}/{total}")
                
            except Exception as e:
                error_msg = f"删除文件时出错 {file_path}: {str(e)}"
                logging.error(error_msg)
                self.update_ui(type='result', text=f"删除失败: {file_path} - {str(e)}\n")

    def start_clean(self):
        if not self.cleanable_files:
            messagebox.showinfo("提示", "没有可清理的文件")
            return

        if not messagebox.askyesno("确认", "确定要删除这些文件吗？此操作不可撤销！"):
            return

        self.result_text.delete("1.0", "end")
        self.update_ui(type='progress', value=0)
        self.update_ui(type='buttons', scan='disabled', clean='disabled')

        def clean_thread():
            try:
                self.clean_files()
                self.update_ui(type='result', text=f"\n清理完成！总共释放空间: {self.format_size(self.total_space_cleared)}")
                self.update_ui(type='buttons', scan='normal', clean='disabled')
                self.update_ui(type='status', text="清理完成")
                self.update_ui(type='progress', value=1)
                messagebox.showinfo("完成", f"清理完成！\n总共释放空间: {self.format_size(self.total_space_cleared)}")
            except Exception as e:
                error_msg = f"清理过程出错: {str(e)}"
                logging.error(error_msg)
                self.update_ui(type='status', text=error_msg)
                messagebox.showerror("错误", error_msg)
                self.update_ui(type='buttons', scan='normal')

        threading.Thread(target=clean_thread, daemon=True).start()

    def get_drives(self):
        """获取所有磁盘信息"""
        drives = []
        try:
            drive_bits = win32api.GetLogicalDrives()
            for letter in range(26):
                if drive_bits & (1 << letter):
                    drive_letter = chr(65 + letter) + ':\\'
                    try:
                        drive_type = win32file.GetDriveType(drive_letter)
                        if drive_type == win32file.DRIVE_FIXED:
                            total_bytes = win32file.GetDiskFreeSpaceEx(drive_letter)[1]
                            free_bytes = win32file.GetDiskFreeSpaceEx(drive_letter)[2]
                            drives.append({
                                'letter': drive_letter,
                                'total': total_bytes,
                                'free': free_bytes,
                                'used': total_bytes - free_bytes
                            })
                    except (win32api.error, pywintypes.error):
                        continue
        except Exception as e:
            logging.error(f"获取磁盘信息失败: {str(e)}")
        return drives

    def update_drive_info(self):
        """更新磁盘信息显示"""
        drive_letter = self.drive_var.get()
        for drive in self.drives:
            if drive['letter'] == drive_letter:
                total_size = self.format_size(drive['total'])
                free_size = self.format_size(drive['free'])
                used_size = self.format_size(drive['used'])
                self.drive_info_label.configure(text=f"总空间: {total_size} | 空闲空间: {free_size} | 已用空间: {used_size}")
                break

    def on_drive_change(self):
        """磁盘选择变更事件"""
        self.update_drive_info()
        self.dir_entry.delete(0, "end")
        self.dir_entry.insert(0, self.drive_var.get())

def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        if sys.platform == 'win32':
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            return

    app = DiskCleaner()
    app.mainloop()

if __name__ == "__main__":
    main()