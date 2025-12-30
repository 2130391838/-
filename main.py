import flet as ft
import json
import random
import requests
import re
from datetime import datetime

# --- 配置 ---
# 注意：安卓上不能直接写死文件路径，我们改用 page.client_storage
DEFAULT_API_KEY = "sk-ncknahphvmzuizmzwdswehemhpzqvugfpeiabhjbapbbdctu"
DEFAULT_API_URL = "https://api.siliconflow.cn/v1/chat/completions"

# --- 辅助函数 ---
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

# --- Flet APP 主程序 ---
def main(page: ft.Page):
    page.title = "云创刷题"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = "adaptive"
    
    # ★★★ 核心修改：使用手机安全存储，防止白屏崩溃 ★★★
    # 初始化数据
    if not page.client_storage.contains_key("tiku_data"):
        page.client_storage.set("tiku_data", [])
        
    # 读取数据
    def get_db():
        return page.client_storage.get("tiku_data") or []
    
    # 保存数据
    def save_db(new_db):
        page.client_storage.set("tiku_data", new_db)

    # 状态变量
    current_q_index = -1
    user_selections = []
    
    # 界面容器
    content_area = ft.Column()
    result_text = ft.Text(size=16, weight="bold")
    
    # --- 渲染题目 ---
    def render_question():
        nonlocal current_q_index, user_selections
        db = get_db() # 实时读取
        
        content_area.controls.clear()
        result_text.value = ""
        user_selections = []
        
        if not db:
            content_area.controls.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.icons.INFO, size=50, color=ft.colors.BLUE),
                    ft.Text("题库是空的", size=20, weight="bold"),
                    ft.Text("请点击底部“导入”按钮，\n让 AI 帮你出题！", text_align="center")
                ], alignment="center", horizontal_alignment="center"),
                padding=50, alignment=ft.alignment.center
            ))
            page.update()
            return

        # 随机抽题
        if current_q_index == -1 or current_q_index >= len(db):
            current_q_index = random.randint(0, len(db)-1)
        
        q = db[current_q_index]
        
        # 题目区域
        content_area.controls.append(ft.Container(
            content=ft.Column([
                ft.Text(f"[{q['type']}]", color=ft.colors.BLUE, weight="bold"),
                ft.Text(q['content'], size=18, weight="w500"),
            ]),
            padding=10,
            border=ft.border.all(1, ft.colors.GREY_300),
            border_radius=10
        ))
        
        content_area.controls.append(ft.Divider(height=20, color="transparent"))
        
        # 选项区域
        options_col = ft.Column()
        is_multi = "多" in q['type']
        
        def on_select(e, label):
            nonlocal user_selections
            if is_multi:
                if e.control.value: user_selections.append(label)
                else: user_selections.remove(label)
            else:
                user_selections = [label]
            
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
            
        # 按钮区域
        def submit_answer(e):
            user_ans = "".join(sorted(user_selections))
            correct_ans = "".join(sorted(q['correctArr'])) if 'correctArr' in q else q['answer']
            
            if user_ans == correct_ans:
                result_text.value = f"🎉 回答正确！"
                result_text.color = ft.colors.GREEN
            else:
                result_text.value = f"❌ 错误\n你的选择：{user_ans}\n正确答案：{correct_ans}"
                result_text.color = ft.colors.RED
            page.update()

        def next_question(e):
            nonlocal current_q_index
            current_q_index = random.randint(0, len(get_db())-1)
            render_question()
            page.update()

        content_area.controls.append(ft.Divider())
        content_area.controls.append(ft.Row([
            ft.ElevatedButton("提交", on_click=submit_answer, bgcolor=ft.colors.BLUE, color="white"),
            ft.OutlinedButton("下一题", on_click=next_question)
        ], alignment="center"))
        content_area.controls.append(ft.Container(content=result_text, padding=10, alignment=ft.alignment.center))
        page.update()

    # --- 导航逻辑 ---
    def nav_change(e):
        index = e.control.selected_index
        content_area.controls.clear()
        
        if index == 0:
            render_question()
            
        elif index == 1:
            txt_input = ft.TextField(label="粘贴题目文本", multiline=True, min_lines=8, hint_text="在这里粘贴乱七八糟的题目文本...")
            status_txt = ft.Text()
            
            def run_import(e):
                if not txt_input.value: return
                status_txt.value = "🤖 AI 正在拼命识别中 (需要联网)..."
                page.update()
                
                new_qs, log = call_ai_import(txt_input.value, DEFAULT_API_KEY, "Qwen/Qwen2.5-32B-Instruct")
                
                if new_qs:
                    db = get_db()
                    count = 0
                    fingerprints = {get_text_fingerprint(x['content']) for x in db}
                    for nq in new_qs:
                        fp = get_text_fingerprint(nq['content'])
                        if fp not in fingerprints:
                            nq['correctArr'] = sorted(list(nq['answer']))
                            db.append(nq)
                            fingerprints.add(fp)
                            count += 1
                    save_db(db) # 保存到手机存储
                    status_txt.value = f"✅ 成功导入 {count} 道新题！\n(重复题目已自动过滤)"
                    status_txt.color = ft.colors.GREEN
                else:
                    status_txt.value = f"❌ 识别失败，请检查网络。\nAI 日志: {log[:100]}..."
                    status_txt.color = ft.colors.RED
                page.update()

            content_area.controls.append(ft.Text("AI 智能导题", size=20, weight="bold"))
            content_area.controls.append(txt_input)
            content_area.controls.append(ft.ElevatedButton("开始识别", on_click=run_import, width=200))
            content_area.controls.append(status_txt)
            page.update()
            
        elif index == 2:
            db = get_db()
            content_area.controls.append(ft.Text("关于", size=30, weight="bold"))
            content_area.controls.append(ft.Text("集成云创刷题App", size=20))
            content_area.controls.append(ft.Text(f"当前题库总数：{len(db)} 题"))
            content_area.controls.append(ft.Divider())
            content_area.controls.append(ft.Text("开发者：by-CCZU赵海博"))
            
            def clear_data(e):
                page.client_storage.clear()
                page.snack_bar = ft.SnackBar(ft.Text("数据已清空"))
                page.snack_bar.open = True
                page.update()
                
            content_area.controls.append(ft.ElevatedButton("清空所有题目", on_click=clear_data, color="red"))
            page.update()

    page.navigation_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationDestination(icon=ft.icons.QUIZ, label="刷题"),
            ft.NavigationDestination(icon=ft.icons.UPLOAD, label="导入"),
            ft.NavigationDestination(icon=ft.icons.INFO, label="关于"),
        ],
        on_change=nav_change
    )
    
    render_question()
    page.add(content_area)

ft.app(target=main)
