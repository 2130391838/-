import flet as ft
import json
import os
import random
import requests
import re
from datetime import datetime

# --- 配置 ---
DB_FILE = 'tiku.json'
DEFAULT_API_KEY = "sk-ncknahphvmzuizmzwdswehemhpzqvugfpeiabhjbapbbdctu"
DEFAULT_API_URL = "https://api.siliconflow.cn/v1/chat/completions"

# --- 核心逻辑函数 (完全复用你之前的) ---
def load_db():
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_text_fingerprint(text):
    if not text: return ""
    return re.sub(r'[^\w\u4e00-\u9fa5]+', '', text).lower()

def call_ai_import(text, api_key, model):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    prompt = """
    你是一个数据提取程序。将用户文本提取为JSON数组。
    目标格式: [{"type":"单选/多选/判断","content":"...","options":[{"label":"A","text":"..."}],"answer":"A"}]
    注意双引号转义。忽略无关文本。
    """
    data = {
        "model": model,
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": f"文本:\n{text[:10000]}"}],
        "temperature": 0.1, "max_tokens": 4096
    }
    try:
        response = requests.post(DEFAULT_API_URL, headers=headers, json=data, timeout=60)
        if response.status_code != 200: return [], str(response.text)
        content = response.json()['choices'][0]['message']['content'].replace('```json', '').replace('```', '').strip()
        if not content.endswith(']'): content = content[:content.rfind('}')+1] + ']'
        return json.loads(content), content
    except Exception as e:
        return [], str(e)

# --- Flet APP 界面 ---
def main(page: ft.Page):
    page.title = "集成云创刷题App"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = "adaptive"
    
    # 全局状态
    db = load_db()
    current_q_index = -1
    user_selections = []
    
    # --- 界面组件引用 ---
    content_area = ft.Column()
    result_text = ft.Text(size=16, weight="bold")
    
    # --- 功能：刷新题目显示 ---
    def render_question():
        nonlocal current_q_index, user_selections
        content_area.controls.clear()
        result_text.value = ""
        user_selections = []
        
        if not db:
            content_area.controls.append(ft.Text("题库为空，请去'导入'页添加题目"))
            page.update()
            return

        if current_q_index == -1 or current_q_index >= len(db):
            current_q_index = random.randint(0, len(db)-1)
        
        q = db[current_q_index]
        
        # 题目类型和内容
        content_area.controls.append(ft.Text(f"[{q['type']}]", color=ft.colors.BLUE, weight="bold"))
        content_area.controls.append(ft.Text(q['content'], size=18))
        content_area.controls.append(ft.Divider())
        
        # 选项
        options_col = ft.Column()
        is_multi = "多" in q['type']
        
        # 选项点击回调
        def on_select(e, label):
            nonlocal user_selections
            if is_multi:
                if e.control.value: user_selections.append(label)
                else: user_selections.remove(label)
            else:
                user_selections = [label] # 单选只能有一个
            
        # 渲染选项
        radio_group = ft.RadioGroup(content=options_col, on_change=lambda e: on_select(None, e.control.value))
        
        for opt in q['options']:
            label_text = f"{opt['label']}. {opt['text']}"
            if is_multi:
                options_col.controls.append(
                    ft.Checkbox(label=label_text, on_change=lambda e, l=opt['label']: on_select(e, l))
                )
            else:
                options_col.controls.append(
                    ft.Radio(value=opt['label'], label=label_text)
                )
        
        if not is_multi:
            content_area.controls.append(radio_group)
        else:
            content_area.controls.append(options_col)
            
        # 提交按钮
        def submit_answer(e):
            user_ans = "".join(sorted(user_selections))
            correct_ans = "".join(sorted(q['correctArr'])) if 'correctArr' in q else q['answer']
            
            if user_ans == correct_ans:
                result_text.value = f"🎉 正确！答案是 {correct_ans}"
                result_text.color = ft.colors.GREEN
            else:
                result_text.value = f"❌ 错误。选了 {user_ans}，答案是 {correct_ans}"
                result_text.color = ft.colors.RED
            page.update()

        # 下一题按钮
        def next_question(e):
            nonlocal current_q_index
            current_q_index = random.randint(0, len(db)-1)
            render_question()
            page.update()

        btn_row = ft.Row([
            ft.ElevatedButton("提交答案", on_click=submit_answer),
            ft.ElevatedButton("下一题", on_click=next_question, icon=ft.icons.ARROW_FORWARD)
        ])
        
        content_area.controls.append(ft.Divider())
        content_area.controls.append(btn_row)
        content_area.controls.append(result_text)
        page.update()

    # --- 页面切换逻辑 ---
    def nav_change(e):
        index = e.control.selected_index
        content_area.controls.clear()
        
        if index == 0: # 刷题页
            render_question()
            
        elif index == 1: # 导入页
            txt_input = ft.TextField(label="粘贴文本", multiline=True, min_lines=5)
            status_txt = ft.Text()
            
            def run_import(e):
                status_txt.value = "AI 正在思考... (请稍等)"
                page.update()
                new_qs, log = call_ai_import(txt_input.value, DEFAULT_API_KEY, "Qwen/Qwen2.5-32B-Instruct")
                if new_qs:
                    count = 0
                    fingerprints = {get_text_fingerprint(x['content']) for x in db}
                    for nq in new_qs:
                        fp = get_text_fingerprint(nq['content'])
                        if fp not in fingerprints:
                            nq['correctArr'] = sorted(list(nq['answer']))
                            db.append(nq)
                            fingerprints.add(fp)
                            count += 1
                    save_db(db)
                    status_txt.value = f"导入成功：{count} 题"
                    status_txt.color = ft.colors.GREEN
                else:
                    status_txt.value = "导入失败，请检查文本"
                    status_txt.color = ft.colors.RED
                page.update()

            content_area.controls.append(ft.Text("AI 导入 (默认 32B 模型)", size=20))
            content_area.controls.append(txt_input)
            content_area.controls.append(ft.ElevatedButton("开始导入", on_click=run_import))
            content_area.controls.append(status_txt)
            page.update()
            
        elif index == 2: # 关于
            content_area.controls.append(ft.Text("集成云创刷题App", size=30, weight="bold"))
            content_area.controls.append(ft.Text("开发者：by-CCZU赵海博", size=20))
            content_area.controls.append(ft.Text("感谢您的使用，多多支持！"))
            page.update()

    # --- 底部导航栏 ---
    page.navigation_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationDestination(icon=ft.icons.QUIZ, label="刷题"),
            ft.NavigationDestination(icon=ft.icons.UPLOAD, label="导入"),
            ft.NavigationDestination(icon=ft.icons.INFO, label="关于"),
        ],
        on_change=nav_change
    )
    
    # 启动默认加载第一页
    render_question()
    page.add(content_area)

ft.app(target=main)