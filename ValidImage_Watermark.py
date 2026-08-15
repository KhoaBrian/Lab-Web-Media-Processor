import os
import queue
import math
import webbrowser
import threading
import concurrent.futures
import tkinter as tk
from tkinter import messagebox, ttk, filedialog, colorchooser
from PIL import Image, ImageDraw, ImageFont, ImageTk

input_folder = 'image'
output_folder = 'optimized'
valid_extensions = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.gif')

def convert_hex_to_rgb(hex_string):
    hex_string = hex_string.replace('#', '')
    return tuple(int(hex_string[i:i+2], 16) for i in (0, 2, 4))

def create_watermark_layer(img_w, img_h, watermark_text, zoom_scale=4, stroke_color="#000000", opacity_percent=50, 
                             text_color="#FFFFFF", text_size_percent=3, border_thick=2):
    x1, y1 = img_w * (2/3), img_h
    x2, y2 = img_w, img_h - (img_h * (3/4))
    
    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
    rotation_angle = math.degrees(math.atan2(y1 - y2, x2 - x1))
    repeated_text = (watermark_text + "   •   ") * 20 
    
    base_size = max(10, int(img_w * (text_size_percent / 100.0)))
    final_font_size = base_size * zoom_scale
    
    try: 
        selected_font = ImageFont.truetype("arial.ttf", final_font_size)
    except OSError: 
        selected_font = ImageFont.load_default()
        
    dummy_canvas = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    text_box = dummy_canvas.textbbox((0, 0), repeated_text, font=selected_font)
    text_width, text_height = text_box[2] - text_box[0], text_box[3] - text_box[1]
    
    padding = 20 * zoom_scale
    text_layer = Image.new('RGBA', (text_width + padding, text_height + padding), (255, 255, 255, 0))
    drawing_tool = ImageDraw.Draw(text_layer)
    
    fill_color = convert_hex_to_rgb(text_color) + (255,)         
    stroke_fill_color = convert_hex_to_rgb(stroke_color) + (255,)        
    
    drawing_tool.text((padding//2, padding//2), repeated_text, font=selected_font, fill=fill_color,
                      stroke_width=border_thick * zoom_scale, stroke_fill=stroke_fill_color)        
    
    rotated_text_layer = text_layer.rotate(rotation_angle, resample=Image.Resampling.BICUBIC, expand=True)        
    final_width, final_height = rotated_text_layer.width // zoom_scale, rotated_text_layer.height // zoom_scale
    
    crisp_text_layer = rotated_text_layer.resize((final_width, final_height), Image.Resampling.LANCZOS)
    
    if opacity_percent < 100:
        alpha_channel = crisp_text_layer.getchannel('A')
        alpha_channel = alpha_channel.point(lambda p: int(p * (opacity_percent / 100.0)))
        crisp_text_layer.putalpha(alpha_channel)
    
    final_watermark = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 0))
    paste_x, paste_y = int(center_x - final_width / 2), int(center_y - final_height / 2)
    final_watermark.paste(crisp_text_layer, (paste_x, paste_y), crisp_text_layer)        
    
    return final_watermark

def apply_manual_texts(source_img, text_items_list):
    drawing_tool = ImageDraw.Draw(source_img)
    for text_item in text_items_list:
        try: 
            selected_font = ImageFont.truetype("arial.ttf", text_item['size'])
        except OSError: 
            selected_font = ImageFont.load_default()
        drawing_tool.text((text_item['x'], text_item['y']), text_item['text'], font=selected_font, fill=text_item['color'])
    return source_img

def generate_sequence_string(mode_type, start_value, interval_value, step_index, prefix_str="", suffix_str=""):
    if mode_type == "Normal": 
        return prefix_str
        
    current_value = start_value + (interval_value * step_index)
    
    if mode_type == "Time (00:00)":
        return f"{prefix_str}{current_value // 60:02d}:{current_value % 60:02d}{suffix_str}"
    elif mode_type == "Time (00:00:00)":
        return f"{prefix_str}{current_value // 3600:02d}:{(current_value % 3600) // 60:02d}:{current_value % 60:02d}{suffix_str}"
    elif mode_type == "Number (0)":
        return f"{prefix_str}{current_value}{suffix_str}"
    return ""

class TextEditorWindow(tk.Toplevel):
    def __init__(self, main_parent, image_paths_list, start_index, custom_data_dict, save_callback_func):
        super().__init__(main_parent)
        self.transient(main_parent)
        self.title("Edit Text And Keyframes")
        self.geometry("1050x700")
        
        self.image_paths_list = image_paths_list
        self.current_index = start_index
        self.custom_data_dict = custom_data_dict
        self.save_callback_func = save_callback_func
        
        self.text_mode = tk.StringVar(value="Normal")
        self.prefix_input = tk.StringVar(value="")
        self.suffix_input = tk.StringVar(value="")
        self.start_input = tk.StringVar(value="0")
        self.interval_input = tk.StringVar(value="10")
        self.pos_x_input = tk.StringVar(value="50")
        self.pos_y_input = tk.StringVar(value="50")
        self.size_input = tk.StringVar(value="40")
        self.current_text_color = "#FF0000"
        self.enable_draft_preview = tk.BooleanVar(value=False) 
        
        for var in (self.text_mode, self.prefix_input, self.suffix_input, self.start_input, 
                    self.interval_input, self.pos_x_input, self.pos_y_input, self.size_input, self.enable_draft_preview):
            var.trace_add("write", lambda *args: self.refresh_preview())
            
        self.load_current_image_data()
        self.build_user_interface()
        self.refresh_preview()

    def load_current_image_data(self):
        self.current_image_path = self.image_paths_list[self.current_index]
        self.original_image = Image.open(self.current_image_path).convert("RGB")
        self.image_width, self.image_height = self.original_image.size
        
        if self.current_image_path not in self.custom_data_dict:
            self.custom_data_dict[self.current_image_path] = []
        self.current_text_list = self.custom_data_dict[self.current_image_path]

    def build_user_interface(self):
        left_panel = ttk.Frame(self, width=380)
        left_panel.pack(side='left', fill='y', padx=10, pady=10)
        
        input_group = ttk.LabelFrame(left_panel, text="Input Text")
        input_group.pack(fill='x', pady=5, ipady=5)
        
        ttk.Label(input_group, text="Format:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        mode_dropdown = ttk.Combobox(input_group, textvariable=self.text_mode, values=["Normal", "Number (0)", "Time (00:00)", "Time (00:00:00)"], state="readonly", width=16)
        mode_dropdown.grid(row=0, column=1, columnspan=3, padx=5, sticky='w')
        
        ttk.Label(input_group, text="Prefix:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        ttk.Entry(input_group, textvariable=self.prefix_input, width=12).grid(row=1, column=1, padx=5, sticky='w')
        
        ttk.Label(input_group, text="Suffix:").grid(row=1, column=2, padx=5, sticky='w')
        ttk.Entry(input_group, textvariable=self.suffix_input, width=12).grid(row=1, column=3, padx=5, sticky='w')
        
        ttk.Label(input_group, text="Start:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        ttk.Spinbox(input_group, from_=0, to=999999, textvariable=self.start_input, width=10).grid(row=2, column=1, padx=5, sticky='w')
        
        ttk.Label(input_group, text="Interval:").grid(row=2, column=2, padx=5, sticky='w')
        ttk.Spinbox(input_group, from_=0, to=999999, textvariable=self.interval_input, width=10).grid(row=2, column=3, padx=5, sticky='w')
        
        self.apply_to_all_checkbox = tk.BooleanVar(value=False)
        ttk.Checkbutton(input_group, text="Apply for all subsequent images", variable=self.apply_to_all_checkbox).grid(row=3, column=0, columnspan=4, padx=5, pady=5, sticky='w')

        visual_group = ttk.LabelFrame(left_panel, text="Position And Style")
        visual_group.pack(fill='x', pady=5)
        
        ttk.Checkbutton(visual_group, text="Show Draft", variable=self.enable_draft_preview).pack(anchor='w', padx=5, pady=5)
        
        row_one = ttk.Frame(visual_group)
        row_one.pack(fill='x', pady=5, padx=5)
        ttk.Label(row_one, text="Pos X:").pack(side='left')
        self.spinbox_x = ttk.Spinbox(row_one, from_=0, to=self.image_width, textvariable=self.pos_x_input, width=6)
        self.spinbox_x.pack(side='left', padx=5)
        ttk.Label(row_one, text="Pos Y:").pack(side='left')
        self.spinbox_y = ttk.Spinbox(row_one, from_=0, to=self.image_height, textvariable=self.pos_y_input, width=6)
        self.spinbox_y.pack(side='left', padx=5)
        
        row_two = ttk.Frame(visual_group)
        row_two.pack(fill='x', pady=5, padx=5)
        ttk.Label(row_two, text="Size:").pack(side='left')
        ttk.Spinbox(row_two, from_=10, to=500, textvariable=self.size_input, width=6).pack(side='left', padx=5)
        self.color_picker_btn = tk.Button(row_two, text="Choose Color", bg=self.current_text_color, fg="white", command=self.open_color_picker)
        self.color_picker_btn.pack(side='left', padx=15)
        
        ttk.Button(left_panel, text="➕ ADD TO IMAGE", command=self.add_text_item).pack(fill='x', pady=10)
        
        ttk.Label(left_panel, text="Current Texts:").pack(anchor='w', pady=2)
        self.text_listbox = tk.Listbox(left_panel, height=5)
        self.text_listbox.pack(fill='x', pady=2)
        
        ttk.Button(left_panel, text="❌ Delete Selected", command=self.remove_text_item).pack(fill='x', pady=2)
        ttk.Button(left_panel, text="💾 SAVE", command=self.save_and_close).pack(fill='x', pady=15)
        self.update_listbox_display()

        right_panel = ttk.Frame(self)
        right_panel.pack(side='right', fill='both', expand=True, padx=10, pady=10)
        
        navigation_panel = ttk.Frame(right_panel)
        navigation_panel.pack(fill='x', pady=5)
        
        self.prev_button = ttk.Button(navigation_panel, text="⬅ Back", command=self.navigate_previous)
        self.prev_button.pack(side='left')
        self.image_info_label = ttk.Label(navigation_panel, text="", font=("Arial", 10, "bold"), foreground="blue")
        self.image_info_label.pack(side='left', expand=True)
        self.next_button = ttk.Button(navigation_panel, text="Next ➡", command=self.navigate_next)
        self.next_button.pack(side='right')

        self.image_preview_label = tk.Label(right_panel, bg="#EFEFEF")
        self.image_preview_label.pack(expand=True, fill='both', pady=5)
        
        self.image_preview_label.bind("<MouseWheel>", self.handle_mouse_scroll)
        self.image_preview_label.bind("<Button-4>", lambda e: self.navigate_previous())
        self.image_preview_label.bind("<Button-5>", lambda e: self.navigate_next())

    def update_header_information(self):
        file_name = os.path.basename(self.current_image_path)
        self.image_info_label.config(text=f"[{self.current_index + 1} / {len(self.image_paths_list)}]  {file_name} ({self.image_width}x{self.image_height} px)")
        self.prev_button.config(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_index < len(self.image_paths_list) - 1 else tk.DISABLED)
        self.spinbox_x.config(to=self.image_width)
        self.spinbox_y.config(to=self.image_height)

    def navigate_previous(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image_data()
            self.update_listbox_display()
            self.refresh_preview()

    def navigate_next(self):
        if self.current_index < len(self.image_paths_list) - 1:
            self.current_index += 1
            self.load_current_image_data()
            self.update_listbox_display()
            self.refresh_preview()

    def handle_mouse_scroll(self, event):
        if event.delta > 0: self.navigate_previous()
        else: self.navigate_next()

    def open_color_picker(self):
        selected_color = colorchooser.askcolor(title="Choose Color", parent=self)[1]
        if selected_color:
            self.current_text_color = selected_color
            self.color_picker_btn.config(bg=self.current_text_color)
            self.refresh_preview()
            
    def parse_integer_value(self, string_number, default_val=0):
        try: return int(string_number)
        except ValueError: return default_val

    def add_text_item(self):
        current_mode = self.text_mode.get()
        prefix = self.prefix_input.get()
        if current_mode == "Normal" and not prefix:
            messagebox.showwarning("Warning", "Please enter text in the Prefix field.")
            return
            
        start_val, interval_val = self.parse_integer_value(self.start_input.get(), 0), self.parse_integer_value(self.interval_input.get(), 1)
        base_data = {
            'x': self.parse_integer_value(self.pos_x_input.get(), 50),
            'y': self.parse_integer_value(self.pos_y_input.get(), 50),
            'size': self.parse_integer_value(self.size_input.get(), 40),
            'color': self.current_text_color
        }
        
        base_data['text'] = generate_sequence_string(current_mode, start_val, interval_val, 0, prefix, self.suffix_input.get())
        self.current_text_list.append(base_data)
        
        if self.apply_to_all_checkbox.get() and current_mode != "Normal":
            for step, i in enumerate(range(self.current_index + 1, len(self.image_paths_list)), 1):
                target_path = self.image_paths_list[i]
                seq_text = generate_sequence_string(current_mode, start_val, interval_val, step, prefix, self.suffix_input.get())
                if target_path not in self.custom_data_dict:
                    self.custom_data_dict[target_path] = []
                self.custom_data_dict[target_path].append({**base_data, 'text': seq_text})
            messagebox.showinfo("Success", "Applied sequence to all subsequent images.")

        self.enable_draft_preview.set(False)
        self.update_listbox_display()
        self.refresh_preview()

    def remove_text_item(self):
        selection = self.text_listbox.curselection()
        if selection:
            self.current_text_list.pop(selection[0])
            self.update_listbox_display()
            self.refresh_preview()

    def update_listbox_display(self):
        self.text_listbox.delete(0, tk.END)
        for item in self.current_text_list:
            self.text_listbox.insert(tk.END, f"{item['text']} (X:{item['x']}, Y:{item['y']})")

    def refresh_preview(self):
        self.update_header_information()
        temp_image = apply_manual_texts(self.original_image.copy(), self.current_text_list)
        
        if self.enable_draft_preview.get():
            draft_text = generate_sequence_string(
                self.text_mode.get(), self.parse_integer_value(self.start_input.get(), 0), 
                self.parse_integer_value(self.interval_input.get(), 1), 0, 
                self.prefix_input.get(), self.suffix_input.get()
            )
            if draft_text:
                draw = ImageDraw.Draw(temp_image)
                try: font = ImageFont.truetype("arial.ttf", self.parse_integer_value(self.size_input.get(), 40))
                except OSError: font = ImageFont.load_default()
                draw.text((self.parse_integer_value(self.pos_x_input.get(), 50), self.parse_integer_value(self.pos_y_input.get(), 50)), draft_text, font=font, fill=self.current_text_color)
        
        temp_image.thumbnail((650, 600), Image.Resampling.LANCZOS)
        self.preview_image_tk = ImageTk.PhotoImage(temp_image)
        self.image_preview_label.config(image=self.preview_image_tk)

    def save_and_close(self):
        self.save_callback_func()
        self.destroy()

class LabAssetWatermarker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Web Media Preparation Tool")
        self.geometry("720x820") 
        self.resizable(False, False)
        
        self.global_text_data = {} 
        self.animation_image_list = []
        self.about_window_instance = None
        
        self.batch_queue = queue.Queue()
        self.anim_queue = queue.Queue()
        
        ttk.Style().configure("TButton", font=("Arial", 10, "bold"), padding=5)
        
        bottom_panel = ttk.Frame(self)
        bottom_panel.pack(side='bottom', fill='x', padx=10, pady=5)
        ttk.Button(bottom_panel, text="ℹ About", width=8, command=self.open_about_window).pack(side='right')
        
        main_notebook = ttk.Notebook(self)
        main_notebook.pack(expand=True, fill='both', padx=10, pady=5)
        
        batch_tab = ttk.Frame(main_notebook)
        main_notebook.add(batch_tab, text="Batch Optimize")
        self.initialize_batch_tab(batch_tab)
        
        animation_tab = ttk.Frame(main_notebook)
        main_notebook.add(animation_tab, text="Create Animation")
        self.initialize_animation_tab(animation_tab)

    def open_about_window(self):
        if self.about_window_instance and self.about_window_instance.winfo_exists():
            self.about_window_instance.lift()
            return
            
        self.about_window_instance = tk.Toplevel(self)
        self.about_window_instance.title("About Lab Media Processor")
        self.about_window_instance.geometry("450x320")
        self.about_window_instance.resizable(False, False)

        ttk.Label(self.about_window_instance, text="Lab Web Media Processor", font=("Arial", 12, "bold")).pack(pady=(15, 5))
        ttk.Label(self.about_window_instance, text="Version: 1.1 | Date: August 2026", font=("Arial", 9, "italic"), foreground="gray").pack(pady=(0, 10))
        
        desc_text = (
            "• Purpose: Automates batch watermarking, compression, and WebP/GIF\n"
            "  conversion for media assets to protect copyright and optimize web loading.\n"
            "• Why: Built to ensure data privacy (offline local processing)\n"
            "  and simplify workflows for wet-lab members without requiring CLI skills."
        )
        desc_label = ttk.Label(self.about_window_instance, text=desc_text, justify=tk.LEFT, font=("Arial", 9))
        desc_label.pack(padx=20, pady=5, anchor='w')
        
        github_url = "https://github.com/KhoaBrian/Lab-Web-Media-Processor"
        link_label = tk.Label(self.about_window_instance, text="🔗 View source code on GitHub", font=("Arial", 10, "underline"), fg="blue", cursor="hand2")
        link_label.pack(pady=15)
        link_label.bind("<Button-1>", lambda e: webbrowser.open_github_repo(github_url) if hasattr(webbrowser, 'open_github_repo') else webbrowser.open(github_url))
        ttk.Button(self.about_window_instance, text="Close", command=self.about_window_instance.destroy).pack(pady=5)

    def select_text_color_batch(self):
        color = colorchooser.askcolor(title="Text Color", parent=self)[1]
        if color: 
            self.batch_text_color_hex = color
            self.batch_text_color_btn.config(bg=color)
            
    def select_border_color_batch(self):
        color = colorchooser.askcolor(title="Border Color", parent=self)[1]
        if color: 
            self.batch_border_color_hex = color
            self.batch_border_color_btn.config(bg=color)
            
    def select_text_color_anim(self):
        color = colorchooser.askcolor(title="Text Color", parent=self)[1]
        if color: 
            self.anim_text_color_hex = color
            self.anim_text_color_btn.config(bg=color)
            
    def select_border_color_anim(self):
        color = colorchooser.askcolor(title="Border Color", parent=self)[1]
        if color: 
            self.anim_border_color_hex = color
            self.anim_border_color_btn.config(bg=color)

    def initialize_batch_tab(self, parent_frame):
        ttk.Label(parent_frame, text="BATCH OPTIMIZE DIRECTORY", font=("Arial", 14, "bold")).pack(pady=15)        
        ttk.Label(parent_frame, text="Place images in 'image' directory. Output will be in 'optimized'.", foreground="gray").pack(pady=(0, 15))
        
        self.enable_webp_conversion = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent_frame, text="Convert to WebP Format", variable=self.enable_webp_conversion).pack(anchor='w', padx=50, pady=5)
        
        wm_frame = ttk.Frame(parent_frame)
        wm_frame.pack(anchor='w', padx=50, pady=5)
        self.enable_batch_watermark = tk.BooleanVar(value=False)
        ttk.Checkbutton(wm_frame, text="Apply Diagonal Watermark:", variable=self.enable_batch_watermark).pack(side='left')
        self.batch_watermark_input = ttk.Entry(wm_frame, width=25)
        self.batch_watermark_input.insert(0, "Ma's Lab - NCU")
        self.batch_watermark_input.pack(side='left', padx=10)
        
        advanced_container = ttk.Frame(parent_frame)
        advanced_container.pack(fill='x', padx=70, pady=5)        
        self.show_advanced_batch = tk.BooleanVar(value=False)
        self.advanced_toggle_btn_batch = ttk.Checkbutton(advanced_container, text="⚙ Show Advanced Options", style="Toolbutton", variable=self.show_advanced_batch, command=self.toggle_advanced_batch)
        self.advanced_toggle_btn_batch.pack(anchor='w')        
        
        self.advanced_settings_group_batch = ttk.LabelFrame(advanced_container, text="Advanced Parameters")
        self.batch_scale_var = tk.StringVar(value="4")
        self.batch_opacity_var = tk.StringVar(value="50")
        self.batch_size_var = tk.StringVar(value="3")
        self.batch_border_var = tk.StringVar(value="2")
        self.batch_threads_var = tk.StringVar(value="4")
        self.batch_text_color_hex = "#FFFFFF"
        self.batch_border_color_hex = "#000000"

        ttk.Label(self.advanced_settings_group_batch, text="Scale:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        ttk.Spinbox(self.advanced_settings_group_batch, from_=1, to=30, textvariable=self.batch_scale_var, width=5).grid(row=0, column=1, sticky='w')
        ttk.Label(self.advanced_settings_group_batch, text="Opac (%):").grid(row=0, column=2, sticky='e', padx=5, pady=5)
        ttk.Spinbox(self.advanced_settings_group_batch, from_=1, to=100, textvariable=self.batch_opacity_var, width=5).grid(row=0, column=3, sticky='w')
        ttk.Label(self.advanced_settings_group_batch, text="Size (%):").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        ttk.Spinbox(self.advanced_settings_group_batch, from_=1, to=100, textvariable=self.batch_size_var, width=5).grid(row=1, column=1, sticky='w')
        ttk.Label(self.advanced_settings_group_batch, text="Border Width:").grid(row=1, column=2, sticky='e', padx=5, pady=5)
        ttk.Spinbox(self.advanced_settings_group_batch, from_=0, to=20, textvariable=self.batch_border_var, width=5).grid(row=1, column=3, sticky='w')
        
        ttk.Label(self.advanced_settings_group_batch, text="CPU Threads:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        ttk.Spinbox(self.advanced_settings_group_batch, from_=1, to=32, textvariable=self.batch_threads_var, width=5).grid(row=2, column=1, sticky='w')
        
        ttk.Label(self.advanced_settings_group_batch, text="Txt Col:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.batch_text_color_btn = tk.Button(self.advanced_settings_group_batch, bg=self.batch_text_color_hex, width=3, command=self.select_text_color_batch)
        self.batch_text_color_btn.grid(row=3, column=1, sticky='w', pady=5)
        ttk.Label(self.advanced_settings_group_batch, text="Brd Col:").grid(row=3, column=2, sticky='e', padx=5, pady=5)
        self.batch_border_color_btn = tk.Button(self.advanced_settings_group_batch, bg=self.batch_border_color_hex, width=3, command=self.select_border_color_batch)
        self.batch_border_color_btn.grid(row=3, column=3, sticky='w', pady=5)
        
        note_text = "Note: Higher Scale = clearer watermark but slower generation.\nMore Threads = faster processing but consumes more RAM."
        note_label = tk.Label(self.advanced_settings_group_batch, text=note_text, fg="red", justify="left", font=("Arial", 9))
        note_label.grid(row=4, column=0, columnspan=4, sticky='w', padx=5, pady=10)
        
        self.batch_progress_bar = ttk.Progressbar(parent_frame, orient="horizontal", length=400, mode="determinate")
        self.batch_progress_bar.pack(pady=15)
        
        self.batch_status_label = ttk.Label(parent_frame, text="Ready for processing.", foreground="green")
        self.batch_status_label.pack(pady=5)
        
        self.execute_batch_btn = ttk.Button(parent_frame, text="Initialize Batch", command=self.start_batch_execution)
        self.execute_batch_btn.pack(pady=10)

    def toggle_advanced_batch(self):
        if self.show_advanced_batch.get():
            self.advanced_toggle_btn_batch.config(text="⚙ Hide Advanced Options")
            self.advanced_settings_group_batch.pack(fill='x', pady=5)
        else:
            self.advanced_toggle_btn_batch.config(text="⚙ Show Advanced Options")
            self.advanced_settings_group_batch.pack_forget()

    def start_batch_execution(self):
        if not os.path.exists(input_folder): 
            messagebox.showerror("System Error", f"Input directory '{input_folder}' not found.")
            return
        
        self.execute_batch_btn.config(state=tk.DISABLED)
        self.batch_progress_bar["value"] = 0
        
        threading.Thread(target=self.batch_processing_worker, args=(self.batch_queue,), daemon=True).start()
        self.poll_batch_queue()

    def poll_batch_queue(self):
        try:
            while True:
                msg = self.batch_queue.get_nowait()
                if msg['type'] == 'progress':
                    self.batch_progress_bar["maximum"] = msg['total']
                    self.batch_progress_bar["value"] = msg['current']
                    self.batch_status_label.config(text=msg['text'])
                    self.update_idletasks() 
                elif msg['type'] == 'done':
                    self.batch_progress_bar["value"] = self.batch_progress_bar["maximum"]
                    self.batch_status_label.config(text="✅ Processing Completed")
                    self.execute_batch_btn.config(state=tk.NORMAL)
                    messagebox.showinfo("Operation Successful", msg['text'])
                    return
                elif msg['type'] == 'error':
                    self.batch_status_label.config(text="❌ Error occurred")
                    self.execute_batch_btn.config(state=tk.NORMAL)
                    messagebox.showerror("Error", msg['text'])
                    return
        except queue.Empty:
            pass
        
        self.after(50, self.poll_batch_queue)

    def batch_processing_worker(self, q):
        os.makedirs(output_folder, exist_ok=True)
        
        grouped_files = {}
        total_files = 0
        
        q.put({'type': 'progress', 'current': 0, 'total': 1, 'text': "Scanning directory headers..."})
        
        for root_dir, _, files in os.walk(input_folder):
            for file_name in files:
                if os.path.splitext(file_name)[1].lower() in valid_extensions:
                    path = os.path.join(root_dir, file_name)
                    try:
                        with Image.open(path) as img:
                            size = img.size
                        
                        if size not in grouped_files:
                            grouped_files[size] = []
                        grouped_files[size].append(path)
                        total_files += 1
                    except Exception as e:
                        print(f"Skipping unreadable file {file_name}: {e}")
        
        if total_files == 0:
            q.put({'type': 'error', 'text': "No valid images detected."})
            return

        try: scale_parameter = int(self.batch_scale_var.get())
        except ValueError: scale_parameter = 4
        try: opacity_parameter = int(self.batch_opacity_var.get())
        except ValueError: opacity_parameter = 50
        try: size_parameter = float(self.batch_size_var.get())
        except ValueError: size_parameter = 3.0
        try: border_parameter = int(self.batch_border_var.get())
        except ValueError: border_parameter = 2
        try: thread_count = int(self.batch_threads_var.get())
        except ValueError: thread_count = 4
        
        signature_text = self.batch_watermark_input.get().strip() or "COPYRIGHT"
        enable_wm = self.enable_batch_watermark.get()
        enable_webp = self.enable_webp_conversion.get()
        
        progress_lock = threading.Lock()
        progress_state = {'current': 0, 'total': total_files}

        def process_size_group(size_tuple, path_list):
            q.put({
                'type': 'progress', 
                'current': progress_state['current'], 
                'total': progress_state['total'], 
                'text': f"Rendering watermark layout for size {size_tuple[0]}x{size_tuple[1]}..."
            })

            watermark_layer = None
            if enable_wm:
                watermark_layer = create_watermark_layer(
                    size_tuple[0], size_tuple[1], signature_text, zoom_scale=scale_parameter, 
                    stroke_color=self.batch_border_color_hex, opacity_percent=opacity_parameter, 
                    text_color=self.batch_text_color_hex, text_size_percent=size_parameter, 
                    border_thick=border_parameter
                )
            
            for original_path in path_list:
                base_name = os.path.basename(original_path)
                new_directory = os.path.join(output_folder, os.path.relpath(os.path.dirname(original_path), input_folder))
                os.makedirs(new_directory, exist_ok=True)
                
                new_file_name = os.path.splitext(base_name)[0] + '.webp' if enable_webp else base_name
                destination_path = os.path.join(new_directory, new_file_name)
                
                try:
                    active_image = Image.open(original_path).convert("RGBA")
                    
                    if watermark_layer:
                        active_image = Image.alpha_composite(active_image, watermark_layer)
                    
                    final_rgb = active_image.convert("RGB")
                    final_rgb.save(destination_path, format='webp' if enable_webp else active_image.format, quality=80)
                    
                except Exception as e: 
                    print(f"Error processing {base_name}: {e}")

                with progress_lock:
                    progress_state['current'] += 1
                    current_val = progress_state['current']

                q.put({
                    'type': 'progress', 
                    'current': current_val, 
                    'total': progress_state['total'], 
                    'text': f"Processed: {current_val}/{progress_state['total']} files..."
                })
            
            if watermark_layer:
                del watermark_layer

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = []
            for sz, paths in grouped_files.items():
                futures.append(executor.submit(process_size_group, sz, paths))
            concurrent.futures.wait(futures)

        q.put({'type': 'done', 'text': f"Batch completed.\nExported {total_files} files to '{output_folder}' directory."})

    def initialize_animation_tab(self, parent_frame):
        ttk.Label(parent_frame, text="GENERATE ANIMATION SEQUENCE", font=("Arial", 14, "bold")).pack(pady=15)
        
        top_container = ttk.Frame(parent_frame)
        top_container.pack(fill='x', padx=20, pady=5)
        
        self.animation_listbox = tk.Listbox(top_container, height=5, selectmode=tk.SINGLE)
        self.animation_listbox.pack(side='left', fill='both', expand=True)
        
        list_controls = ttk.Frame(top_container)
        list_controls.pack(side='left', padx=10)
        ttk.Button(list_controls, text="Add File", command=self.add_image_to_sequence).pack(fill='x', pady=2)
        ttk.Button(list_controls, text="Remove", command=self.remove_image_from_sequence).pack(fill='x', pady=2)
        ttk.Button(list_controls, text="Move Up ⬆", command=lambda: self.reorder_sequence(-1)).pack(fill='x', pady=2)
        ttk.Button(list_controls, text="Move Down ⬇", command=lambda: self.reorder_sequence(1)).pack(fill='x', pady=2)

        self.edit_timestamps_btn = ttk.Button(parent_frame, text="🖋 Modify Overlays & Timestamps", command=self.open_sequence_editor)
        self.edit_timestamps_btn.pack(pady=5)

        export_settings_group = ttk.LabelFrame(parent_frame, text="Export Configuration")
        export_settings_group.pack(fill='x', padx=20, pady=10)
        
        column_left = ttk.Frame(export_settings_group)
        column_left.pack(side='left', padx=15, pady=5, fill='y')
        
        format_frame = ttk.Frame(column_left)
        format_frame.pack(anchor='w', pady=2)
        ttk.Label(format_frame, text="Output Format:").pack(side='left')
        self.export_format_var = tk.StringVar(value=".webp")
        ttk.Combobox(format_frame, textvariable=self.export_format_var, values=[".webp", ".gif"], width=7, state="readonly").pack(side='left', padx=5)

        ttk.Label(column_left, text="Framerate (FPS):").pack(anchor='w', pady=(5,0))
        self.fps_input = ttk.Spinbox(column_left, from_=1, to=60, width=10)
        self.fps_input.set(5)
        self.fps_input.pack(anchor='w', pady=2)
        
        self.enable_infinite_loop = tk.BooleanVar(value=True)
        ttk.Checkbutton(column_left, text="Loop Animation", variable=self.enable_infinite_loop).pack(anchor='w')
        
        column_right = ttk.Frame(export_settings_group)
        column_right.pack(side='left', padx=15, pady=5)
        
        anim_watermark_frame = ttk.Frame(column_right)
        anim_watermark_frame.pack(anchor='w')
        self.enable_anim_watermark = tk.BooleanVar(value=False)
        ttk.Checkbutton(anim_watermark_frame, text="Apply Watermark:", variable=self.enable_anim_watermark).pack(side='left')
        self.anim_watermark_input = ttk.Entry(column_right, width=25)
        self.anim_watermark_input.insert(0, "Ma's Lab - NCU")
        self.anim_watermark_input.pack(anchor='w', pady=2)

        self.show_advanced_anim = tk.BooleanVar(value=False)
        self.advanced_toggle_btn_anim = ttk.Checkbutton(column_right, text="⚙ View Advanced Params", style="Toolbutton", variable=self.show_advanced_anim, command=self.toggle_advanced_anim)
        self.advanced_toggle_btn_anim.pack(anchor='w', pady=5)        
        
        self.advanced_settings_frame_anim = ttk.Frame(column_right)        
        self.anim_scale_var = tk.StringVar(value="4")
        self.anim_opacity_var = tk.StringVar(value="50")
        self.anim_size_var = tk.StringVar(value="3")
        self.anim_border_var = tk.StringVar(value="2")
        self.anim_threads_var = tk.StringVar(value="4")
        self.anim_text_color_hex = "#FFFFFF"
        self.anim_border_color_hex = "#000000"

        ttk.Label(self.advanced_settings_frame_anim, text="Scale:").grid(row=0, column=0, sticky='e', padx=2, pady=2)
        ttk.Spinbox(self.advanced_settings_frame_anim, from_=1, to=30, textvariable=self.anim_scale_var, width=3).grid(row=0, column=1, sticky='w')
        ttk.Label(self.advanced_settings_frame_anim, text="Opac (%):").grid(row=0, column=2, sticky='e', padx=2, pady=2)
        ttk.Spinbox(self.advanced_settings_frame_anim, from_=1, to=100, textvariable=self.anim_opacity_var, width=3).grid(row=0, column=3, sticky='w')
        ttk.Label(self.advanced_settings_frame_anim, text="Size (%):").grid(row=1, column=0, sticky='e', padx=2, pady=2)
        ttk.Spinbox(self.advanced_settings_frame_anim, from_=1, to=100, textvariable=self.anim_size_var, width=3).grid(row=1, column=1, sticky='w')
        ttk.Label(self.advanced_settings_frame_anim, text="Border Width:").grid(row=1, column=2, sticky='e', padx=2, pady=2)
        ttk.Spinbox(self.advanced_settings_frame_anim, from_=0, to=20, textvariable=self.anim_border_var, width=3).grid(row=1, column=3, sticky='w')
        ttk.Label(self.advanced_settings_frame_anim, text="CPU Threads:").grid(row=2, column=0, sticky='e', padx=2, pady=2)
        ttk.Spinbox(self.advanced_settings_frame_anim, from_=1, to=32, textvariable=self.anim_threads_var, width=3).grid(row=2, column=1, sticky='w')
        
        ttk.Label(self.advanced_settings_frame_anim, text="Txt Col:").grid(row=3, column=0, sticky='e', padx=2, pady=2)
        self.anim_text_color_btn = tk.Button(self.advanced_settings_frame_anim, bg=self.anim_text_color_hex, width=2, command=self.select_text_color_anim)
        self.anim_text_color_btn.grid(row=3, column=1, sticky='w')
        ttk.Label(self.advanced_settings_frame_anim, text="Brd Col:").grid(row=3, column=2, sticky='e', padx=2, pady=2)
        self.anim_border_color_btn = tk.Button(self.advanced_settings_frame_anim, bg=self.anim_border_color_hex, width=2, command=self.select_border_color_anim)
        self.anim_border_color_btn.grid(row=3, column=3, sticky='w')

        anim_note = "Note: Higher Scale = clearer watermark but slower generation.\nMore Threads = faster processing but consumes more RAM."
        anim_note_label = tk.Label(self.advanced_settings_frame_anim, text=anim_note, fg="red", justify="left", font=("Arial", 9))
        anim_note_label.grid(row=4, column=0, columnspan=4, sticky='w', pady=5)

        self.anim_progress_bar = ttk.Progressbar(parent_frame, orient="horizontal", length=300, mode="determinate")
        self.anim_progress_bar.pack(pady=10)
        
        self.anim_status_label = ttk.Label(parent_frame, text="Awaiting execution.", foreground="green")
        self.anim_status_label.pack(pady=2)

        self.execute_export_btn = ttk.Button(parent_frame, text="Export Compiled Animation", command=self.initialize_export)
        self.execute_export_btn.pack(pady=5)

    def toggle_advanced_anim(self):
        if self.show_advanced_anim.get():
            self.advanced_toggle_btn_anim.config(text="⚙ Hide Advanced Params")
            self.advanced_settings_frame_anim.pack(anchor='w', pady=2)
        else:
            self.advanced_toggle_btn_anim.config(text="⚙ View Advanced Params")
            self.advanced_settings_frame_anim.pack_forget()

    def add_image_to_sequence(self):
        for target_file in filedialog.askopenfilenames(filetypes=[("Supported Images", "*.jpg *.jpeg *.png *.webp *.tif")]): 
            self.animation_image_list.append(target_file)
            self.animation_listbox.insert(tk.END, os.path.basename(target_file))

    def remove_image_from_sequence(self):
        active_selection = self.animation_listbox.curselection()
        if active_selection: 
            self.animation_listbox.delete(active_selection[0])
            self.animation_image_list.pop(active_selection[0])

    def reorder_sequence(self, direction_offset):
        active_selection = self.animation_listbox.curselection()
        if not active_selection: return
            
        current_index = active_selection[0]
        target_index = current_index + direction_offset
        
        if 0 <= target_index < self.animation_listbox.size():
            item_value = self.animation_listbox.get(current_index)
            self.animation_listbox.delete(current_index)
            self.animation_listbox.insert(target_index, item_value)
            self.animation_listbox.select_set(target_index)
            
            temp_path = self.animation_image_list[current_index]
            self.animation_image_list[current_index] = self.animation_image_list[target_index]
            self.animation_image_list[target_index] = temp_path

    def open_sequence_editor(self):
        if len(self.animation_image_list) == 0:
            messagebox.showwarning("Notice", "Please load files into the sequence first.")
            return
            
        active_selection = self.animation_listbox.curselection()
        active_index = active_selection[0] if active_selection else 0
        TextEditorWindow(self, self.animation_image_list, active_index, self.global_text_data, lambda: None)

    def initialize_export(self):
        if len(self.animation_image_list) < 2: 
            messagebox.showwarning("Requirements Not Met", "Minimum of 2 images required for animation.")
            return
            
        selected_extension = self.export_format_var.get()
        format_description = "GIF Image" if selected_extension == ".gif" else "Animated WebP"
            
        save_destination = filedialog.asksaveasfilename(defaultextension=selected_extension, filetypes=[(format_description, f"*{selected_extension}")])
        if not save_destination: return
            
        self.execute_export_btn.config(state=tk.DISABLED)
        self.anim_progress_bar["value"] = 0
        
        threading.Thread(target=self.animation_generation_worker, args=(save_destination, selected_extension, self.anim_queue), daemon=True).start()
        self.poll_anim_queue()

    def poll_anim_queue(self):
        try:
            while True:
                msg = self.anim_queue.get_nowait()
                if msg['type'] == 'progress':
                    self.anim_progress_bar["maximum"] = msg['total']
                    self.anim_progress_bar["value"] = msg['current']
                    self.anim_status_label.config(text=msg['text'])
                    self.update_idletasks() 
                elif msg['type'] == 'done':
                    self.anim_progress_bar["value"] = self.anim_progress_bar["maximum"]
                    self.anim_status_label.config(text="✅ Export Completed")
                    self.execute_export_btn.config(state=tk.NORMAL)
                    messagebox.showinfo("Export Successful", msg['text'])
                    return
                elif msg['type'] == 'error':
                    self.anim_status_label.config(text="Execution halted due to error.")
                    self.execute_export_btn.config(state=tk.NORMAL)
                    messagebox.showerror("Export Failed", msg['text'])
                    return
        except queue.Empty:
            pass
        self.after(50, self.poll_anim_queue)

    def animation_generation_worker(self, save_destination, file_extension, q):
        total_frames = len(self.animation_image_list)
        
        try: framerate = float(self.fps_input.get())
        except ValueError: framerate = 5.0
        frame_duration_ms = int(1000 / framerate)
        
        try: scale_val = int(self.anim_scale_var.get())
        except ValueError: scale_val = 4
        try: opacity_val = int(self.anim_opacity_var.get())
        except ValueError: opacity_val = 50
        try: size_val = float(self.anim_size_var.get())
        except ValueError: size_val = 3.0
        try: border_val = int(self.anim_border_var.get())
        except ValueError: border_val = 2
        try: thread_count = int(self.anim_threads_var.get())
        except ValueError: thread_count = 4
        
        overlay_text = self.anim_watermark_input.get().strip() or "COPYRIGHT"
        enable_wm = self.enable_anim_watermark.get()

        try:
            with Image.open(self.animation_image_list[0]) as first_image:
                reference_dimensions = first_image.size

            watermark_layer = None
            if enable_wm:
                q.put({'type': 'progress', 'current': 0, 'total': total_frames + 1, 'text': "Generating base watermark layout..."})
                watermark_layer = create_watermark_layer(
                    reference_dimensions[0], reference_dimensions[1], overlay_text, 
                    zoom_scale=scale_val, stroke_color=self.anim_border_color_hex, 
                    opacity_percent=opacity_val, text_color=self.anim_text_color_hex, 
                    text_size_percent=size_val, border_thick=border_val
                )
                
            compiled_frames = [None] * total_frames
            progress_lock = threading.Lock()
            progress_state = {'current': 0}

            def process_animation_frame(idx, path):
                img = Image.open(path).convert("RGBA")
                
                if path in self.global_text_data:
                    img = apply_manual_texts(img, self.global_text_data[path])
                
                if img.size != reference_dimensions:
                    img = img.resize(reference_dimensions, Image.Resampling.LANCZOS)
                
                if watermark_layer:
                    img = Image.alpha_composite(img, watermark_layer)
                    
                final_rgb = img.convert("RGB")
                
                with progress_lock:
                    progress_state['current'] += 1
                    current_val = progress_state['current']
                
                q.put({
                    'type': 'progress', 'current': current_val, 'total': total_frames + 1, 
                    'text': f"Rendering frame {current_val}/{total_frames}..."
                })
                
                return idx, final_rgb

            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [executor.submit(process_animation_frame, i, path) for i, path in enumerate(self.animation_image_list)]
                for future in concurrent.futures.as_completed(futures):
                    idx, frame_data = future.result()
                    compiled_frames[idx] = frame_data
                
            if watermark_layer:
                del watermark_layer
                
            q.put({
                'type': 'progress', 'current': total_frames + 1, 'total': total_frames + 1, 
                'text': "Compiling final output... This process takes time depending on frame count."
            })
            
            output_format = 'gif' if file_extension == '.gif' else 'webp'
            loop_iterations = 0 if self.enable_infinite_loop.get() else 1
                
            compiled_frames[0].save(
                save_destination, format=output_format, save_all=True, append_images=compiled_frames[1:],
                duration=frame_duration_ms, loop=loop_iterations, quality=80, method=4
            )
            
            q.put({'type': 'done', 'text': f"Animation successfully saved to:\n{save_destination}"})
            
        except Exception as error_msg:
            q.put({'type': 'error', 'text': f"An error occurred: {error_msg}"})

if __name__ == "__main__":
    app_instance = LabAssetWatermarker()
    app_instance.mainloop()