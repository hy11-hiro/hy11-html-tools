import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from pdf2image import convert_from_path
import tempfile
import os
import math
import glob
import shutil
from io import BytesIO
from streamlit_image_coordinates import streamlit_image_coordinates
import streamlit.components.v1 as components
import urllib.parse

# ==========================================
# 0. アプリ設定
# ==========================================
st.set_page_config(page_title="Gaikou-Sekisan Pro", layout="wide", page_icon="🏡")

st.markdown("""
<style>
    /* --- レイアウト調整 --- */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 10rem !important;
        max-width: 100% !important;
    }
    header { display: none !important; }
    
    h1 {
        font-size: 1.5rem !important;
        border-bottom: 2px solid #ddd;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        font-family: "Meiryo", "Hiragino Kaku Gothic ProN", sans-serif;
    }

    .stButton button { width: 100%; border-radius: 5px; font-weight: bold; }
    .stNumberInput, .stSelectbox, .stTextInput { margin-bottom: 0px !important; }
    .stDataEditor { font-size: 0.9rem; }
    
    /* サイドバー強調 */
    .sidebar-highlight {
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: bold;
        text-align: center;
        border: 2px solid;
    }

    /* --- 画像エリアのスタイル --- */
    /* iframe自体にスタイルを当てる */
    iframe {
        display: block !important;
        margin: 0 auto !important;
    }
    
    /* カーソル強制 */
    .element-container:has(iframe), iframe {
        cursor: crosshair !important;
    }

    /* ヘッダーオーバーレイ */
    .floating-header {
        position: fixed;
        top: 10px;
        left: 50%; 
        transform: translateX(-50%);
        z-index: 9999;
        background-color: rgba(255, 255, 255, 0.9); 
        backdrop-filter: blur(5px);
        padding: 8px 20px;
        border-radius: 30px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        border: 1px solid rgba(255,255,255,0.5);
        font-family: "Meiryo", sans-serif;
        font-weight: bold;
        color: #5d4037;
        display: flex;
        align-items: center;
        gap: 10px;
        pointer-events: none;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 関数群
# ==========================================

def get_poppler_config():
    """Popplerのパスを自動判定"""
    if shutil.which("pdftoppm"):
        return None # Linux/Cloud環境
    
    patterns = [
        r"C:\Program Files\poppler-*\Library\bin", 
        r"C:\Program Files\poppler-*\bin",
        r"C:\poppler-*\Library\bin",
        r"C:\Users\*\Downloads\poppler-*\Library\bin"
    ]
    for p in patterns:
        found = glob.glob(p)
        if found: return sorted(found, reverse=True)[0]
    return ""

def load_image(uploaded_file, poppler_path):
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    image = None
    try:
        if file_ext == ".pdf":
            if poppler_path is None:
                images = convert_from_path(tmp_path, dpi=200)
            elif poppler_path:
                images = convert_from_path(tmp_path, poppler_path=poppler_path, dpi=200)
            else:
                raise ValueError("Poppler Path Error")
            if images: image = images[0].convert("RGB")
        elif file_ext == ".dxf":
            import ezdxf
            from ezdxf.addons.drawing import RenderContext, Frontend
            from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
            import matplotlib.pyplot as plt
            doc = ezdxf.readfile(tmp_path)
            msp = doc.modelspace()
            fig = plt.figure(dpi=300)
            ax = fig.add_axes([0, 0, 1, 1])
            ctx = RenderContext(doc)
            out = MatplotlibBackend(ax)
            Frontend(ctx, out).draw_layout(msp, finalize=True)
            fig.canvas.draw()
            data = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
            data = data.reshape(fig.canvas.get_width_height()[::-1] + (3,))
            image = Image.fromarray(data).convert("RGB")
            plt.close(fig)
    except Exception as e:
        return None, str(e)
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)
    
    return image, None

def calc_dist(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def calc_poly_area(coords):
    x = [c[0] for c in coords]
    y = [c[1] for c in coords]
    return 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))

def get_font(size=20):
    # サーバー上の日本語フォント対応
    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", # Streamlit Cloud
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

def get_resized_base_image(base_image, zoom):
    if "cached_resized_img" in st.session_state:
        cached_zoom, cached_img, cached_id = st.session_state.cached_resized_img
        if abs(cached_zoom - zoom) < 0.001 and cached_id == id(base_image):
            return cached_img.copy()

    w, h = base_image.size
    new_w = int(w * zoom)
    new_h = int(h * zoom)
    img = base_image.resize((new_w, new_h), Image.Resampling.BICUBIC)
    
    st.session_state.cached_resized_img = (zoom, img, id(base_image))
    return img.copy()

def hex_to_rgb(hex_code, alpha=255):
    hex_code = hex_code.lstrip('#')
    return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)

def draw_overlay(base_image, history, current_points, current_mode, zoom, is_subtraction=False, show_labels=True, current_color="#FF0000", stroke_width=3):
    img = get_resized_base_image(base_image, zoom)
    draw = ImageDraw.Draw(img, "RGBA")
    font_size = max(14, int(16 * zoom)) 
    font = get_font(font_size)
    def to_zoom(pt): return (pt[0] * zoom, pt[1] * zoom)

    for i, item in enumerate(history):
        pts = [to_zoom(p) for p in item['points']]
        label = item.get('label', '')
        is_sub = item.get('is_subtraction', False)
        item_color_hex = item.get('color', '#FF0000')
        item_width = item.get('width', stroke_width)
        base_rgb = hex_to_rgb(item_color_hex)
        
        if item['type'] == 'area':
            if is_sub:
                fill_col = (0, 0, 255, 60)
                outline_col = (0, 0, 180, 200)
                label_prefix = "[-]"
                text_color_hex = "#0000B4"
            else:
                fill_col = (base_rgb[0], base_rgb[1], base_rgb[2], 60)
                outline_col = (base_rgb[0], base_rgb[1], base_rgb[2], 255)
                label_prefix = ""
                text_color_hex = item_color_hex
        else:
            fill_col = None
            outline_col = (base_rgb[0], base_rgb[1], base_rgb[2], 255)
            label_prefix = ""
            text_color_hex = item_color_hex
        
        if len(pts) > 1:
            if item['type'] == 'area':
                draw.polygon(pts, fill=fill_col, outline=outline_col, width=item_width)
            else:
                draw.line(pts, fill=outline_col, width=item_width)
        
        if show_labels and pts:
            start_p = pts[0]
            display_label = f"No.{i+1} {label_prefix}{label}"
            x, y = start_p[0], start_p[1] - font_size - 5
            stroke_w = 2
            for off_x in range(-stroke_w, stroke_w+1):
                for off_y in range(-stroke_w, stroke_w+1):
                    draw.text((x+off_x, y+off_y), display_label, font=font, fill="white")
            draw.text((x, y), display_label, font=font, fill=text_color_hex)
            draw.ellipse((start_p[0]-4, start_p[1]-4, start_p[0]+4, start_p[1]+4), fill="white", outline="black")

    if current_points:
        z_curr = [to_zoom(p) for p in current_points]
        curr_hex = "#0000FF" if is_subtraction else current_color
        curr_rgb = hex_to_rgb(curr_hex)
        curr_outline = (curr_rgb[0], curr_rgb[1], curr_rgb[2], 255)
        for p in z_curr:
            draw.ellipse((p[0]-5, p[1]-5, p[0]+5, p[1]+5), fill=curr_outline, outline="white")
        if len(z_curr) > 1:
            draw.line(z_curr, fill=curr_outline, width=stroke_width)
        if current_mode == "area" and len(z_curr) > 1:
            draw.line([z_curr[-1], z_curr[0]], fill=(50, 50, 50, 100), width=1)

    return img.convert("RGB")

# ==========================================
# 2. メイン処理
# ==========================================
def main():
    if "bg_image" not in st.session_state: st.session_state.bg_image = None
    if "poppler_path" not in st.session_state: st.session_state.poppler_path = get_poppler_config()
    
    if "history" not in st.session_state: st.session_state.history = []
    if "current_points" not in st.session_state: st.session_state.current_points = []
    if "scale_val" not in st.session_state: st.session_state.scale_val = None
    if "last_click" not in st.session_state: st.session_state.last_click = None
    if "zoom_rate" not in st.session_state: st.session_state.zoom_rate = 0.5
    if "custom_items" not in st.session_state: st.session_state.custom_items = []
    if "stroke_width" not in st.session_state: st.session_state.stroke_width = 3

    # ---------------------------
    # 左サイドバー
    # ---------------------------
    with st.sidebar:
        st.markdown("### 🏡 外構積算 Pro")
        
        # 1. ファイル
        with st.expander("📂 ファイル", expanded=True):
            if st.session_state.poppler_path is not None:
                st.session_state.poppler_path = st.text_input("Popplerパス", value=st.session_state.poppler_path)
            
            uploaded = st.file_uploader("PDF / DXF", type=["pdf", "dxf"], label_visibility="collapsed")
            if uploaded and st.button("読込", type="primary", use_container_width=True):
                img, err = load_image(uploaded, st.session_state.poppler_path)
                if img:
                    st.session_state.bg_image = img
                    st.session_state.history = []
                    st.session_state.current_points = []
                    st.session_state.scale_val = None
                    st.session_state.zoom_rate = 0.5
                    if "cached_resized_img" in st.session_state: del st.session_state.cached_resized_img
                    st.success("完了")
                else:
                    st.error(err)
        
        st.divider()

        # 2. 表示設定
        with st.expander("👀 表示", expanded=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                new_zoom = st.number_input("倍率", value=st.session_state.zoom_rate, step=0.1, min_value=0.1, max_value=5.0, format="%.1f")
            with c2:
                if st.button("R", help="倍率リセット"):
                    st.session_state.zoom_rate = 0.5
                    st.rerun()
            if new_zoom != st.session_state.zoom_rate:
                st.session_state.zoom_rate = new_zoom
                st.rerun()
            show_labels = st.checkbox("ラベル", value=True)

        # 3. ツール
        with st.expander("🛠️ 計測", expanded=True):
            mode = st.radio("モード", ["📏 スケール", "📐 距離", "🟥 面積"], label_visibility="collapsed")
            mode_key = "scale" if "スケール" in mode else ("dist" if "距離" in mode else "area")
            
            current_label = ""
            current_color_hex = "#FF0000"
            is_subtraction = False

            if mode_key != "scale":
                if mode_key == "area":
                    sub_check = st.checkbox("➖ 抜き (減算)", value=False)
                    if sub_check: is_subtraction = True

                st.caption("項目")
                default_dist = ["ブロック積", "フェンス", "ブロック＋フェンス", "境界ブロック", "縁石", "土留め"]
                default_area = ["土間コンクリート", "砂利敷き", "人工芝", "防草シート", "タイル"]
                opts = (default_dist if mode_key == "dist" else default_area) + st.session_state.custom_items + ["その他"]
                sel = st.selectbox("選択", opts, label_visibility="collapsed")
                
                # 新規追加エリア (Expanderを使わず直接配置してエラー回避)
                st.caption("➕ 新規項目を入力")
                c_add1, c_add2 = st.columns([3, 1])
                with c_add1:
                    new_item_val = st.text_input("新規追加", placeholder="リストに追加", label_visibility="collapsed", key="new_item_input")
                with c_add2:
                    if st.button("追加"):
                        if new_item_val and new_item_val not in st.session_state.custom_items:
                            st.session_state.custom_items.append(new_item_val)
                            st.toast(f"「{new_item_val}」を追加しました")
                            st.rerun()

                color_map = {
                    "ブロック積": "#8d6e63", "フェンス": "#a1887f", "ブロック＋フェンス": "#558b2f",
                    "土間コンクリート": "#bdbdbd", "砂利敷き": "#ffcc80", "人工芝": "#66bb6a",
                    "防草シート": "#424242", "タイル": "#d7ccc8"
                }
                def_col = color_map.get(sel, "#ef5350")
                
                c_in1, c_in2 = st.columns([3, 1])
                with c_in1:
                    current_label = st.text_input("名称", "追加" if sel=="その他" else sel, label_visibility="collapsed")
                with c_in2:
                    current_color_hex = st.color_picker("色", def_col, label_visibility="collapsed")
                
                st.session_state.stroke_width = st.slider("線の太さ", 1, 10, 3)

                btn_col = "primary" if not is_subtraction else "secondary"
                btn_txt = f"➖ 抜き確定" if is_subtraction else "✅ 確定"
                
                if st.button(btn_txt, type=btn_col, use_container_width=True):
                    if len(st.session_state.current_points) >= 2:
                        st.session_state.history.append({
                            "type": mode_key,
                            "points": st.session_state.current_points,
                            "label": current_label,
                            "is_subtraction": is_subtraction,
                            "color": current_color_hex,
                            "width": st.session_state.stroke_width,
                            "remarks": "",
                            "link": ""
                        })
                        st.session_state.current_points = []
                        st.rerun()
            else:
                st.info("2点クリックして距離を入力")
                real_m = st.number_input("距離(m)", 0.0001, 1000.0, 1.0, 0.0001, format="%.4f")
                if len(st.session_state.current_points) == 2:
                    if st.button("適用", type="primary", use_container_width=True):
                        p1 = st.session_state.current_points[0]
                        p2 = st.session_state.current_points[1]
                        px = calc_dist(p1, p2)
                        if px > 0:
                            st.session_state.scale_val = real_m / px
                            st.session_state.current_points = []
                            st.toast("スケール設定完了")
                            st.rerun()
            
            c_act1, c_act2 = st.columns(2)
            with c_act1:
                if st.button("戻る", use_container_width=True):
                    if st.session_state.current_points: st.session_state.current_points.pop()
                    elif st.session_state.history: st.session_state.history.pop()
                    st.rerun()
            with c_act2:
                if st.button("クリア", use_container_width=True):
                    st.session_state.history = []
                    st.session_state.current_points = []
                    st.rerun()

        # 4. 抜きコピー
        if mode_key == "area" and st.session_state.history:
            st.divider()
            with st.expander("🛠️ 抜きコピー", expanded=False):
                area_opts = [f"No.{i+1} {h['label']}" for i, h in enumerate(st.session_state.history) if h['type']=='area' and not h.get('is_subtraction')]
                if area_opts:
                    target = st.selectbox("元の形", area_opts)
                    sub_label = st.text_input("抜き先の名称", value="砂利敷き")
                    if st.button("この形で抜く"):
                        idx = int(target.split(" ")[0].replace("No.", "")) - 1
                        new_item = st.session_state.history[idx].copy()
                        new_item['is_subtraction'] = True
                        new_item['label'] = sub_label
                        st.session_state.history.append(new_item)
                        st.success("追加しました")
                        st.rerun()

    # ---------------------------
    # メインエリア
    # ---------------------------
    if st.session_state.bg_image:
        # ヘッダー
        mode_name = "📏 スケール" if mode_key == "scale" else ("📐 距離" if mode_key == "dist" else "🟥 面積")
        st.markdown(f"""
            <div class="floating-header">
                <span>{mode_name}</span>
                <span style="font-weight:normal; font-size:0.8em;">｜ 倍率: {st.session_state.zoom_rate}x</span>
            </div>
        """, unsafe_allow_html=True)

        col_draw, col_list = st.columns([7, 3])
        
        # 図面エリア
        with col_draw:
            zoom = st.session_state.zoom_rate
            display_img = draw_overlay(
                st.session_state.bg_image, 
                st.session_state.history, 
                st.session_state.current_points,
                mode_key,
                zoom,
                is_subtraction,
                show_labels,
                current_color_hex,
                st.session_state.stroke_width
            )
            
            # ★重要: エラーの原因だった「生のHTML枠」を廃止し、
            # Streamlit純正のコンテナでラップしてスクロール可能にする
            with st.container(height=650, border=True):
                value = streamlit_image_coordinates(display_img, key="main_click")
                
                # スクロール維持JS (純正コンテナ対応)
                # st.container(height=...) はCSSクラス .st-key-[key] ではなく
                # 特定の構造を持つため、JSでそのスクロール位置を制御する
                scroll_js = """
                <script>
                    (function() {
                        // スクロール可能なコンテナを探す (height指定されたstVerticalBlock)
                        const containers = document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlock"]');
                        // 図面が入っているコンテナはおそらく一番大きい、または特定の場所にあるもの
                        // ここではすべてのスクロール可能要素の位置を保存・復元する「総当たり作戦」でいく
                        
                        const key = 'st_scroll_positions';

                        function saveScroll() {
                            const positions = [];
                            document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"] > div').forEach((el, idx) => {
                                positions.push(el.scrollTop + ',' + el.scrollLeft);
                            });
                            sessionStorage.setItem(key, JSON.stringify(positions));
                        }

                        function restoreScroll() {
                            const saved = sessionStorage.getItem(key);
                            if (saved) {
                                const positions = JSON.parse(saved);
                                document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"] > div').forEach((el, idx) => {
                                    if (positions[idx]) {
                                        const [top, left] = positions[idx].split(',');
                                        el.scrollTop = parseInt(top);
                                        el.scrollLeft = parseInt(left);
                                    }
                                    el.addEventListener('scroll', saveScroll);
                                });
                            }
                        }
                        
                        // 実行
                        setTimeout(restoreScroll, 100);
                        setTimeout(restoreScroll, 500);
                    })();
                </script>
                """
                components.html(scroll_js, height=0)

            if value and value != st.session_state.last_click:
                st.session_state.last_click = value
                raw_x = value["x"] / zoom
                raw_y = value["y"] / zoom
                st.session_state.current_points.append((raw_x, raw_y))
                st.rerun()

        # 集計エリア
        with col_list:
            if st.session_state.scale_val:
                scale = st.session_state.scale_val
                editor_data = []
                for i, item in enumerate(st.session_state.history):
                    val = 0
                    pts = item['points']
                    if item['type'] == 'dist':
                        d_px = 0
                        for j in range(len(pts)-1): d_px += calc_dist(pts[j], pts[j+1])
                        val = d_px * scale
                    elif item['type'] == 'area':
                        if len(pts) >= 3: val = calc_poly_area(pts) * (scale**2)
                    
                    is_sub = item.get('is_subtraction', False)
                    val_str = f"▲ {val:.2f}" if is_sub else f"{val:.2f}"
                    
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote(item.get('label', ''))}"
                    
                    editor_data.append({
                        "No": i+1,
                        "項目": item.get('label', ''),
                        "値": val_str,
                        "単位": "m" if item['type']=='dist' else "㎡",
                        "抜": is_sub,
                        "🔍": search_url, 
                        "🔗 リンク": item.get('link', ''),
                        "備考": item.get('remarks', ''),
                        "idx": i
                    })
                
                st.markdown('<div class="ui-card">', unsafe_allow_html=True)
                st.markdown("##### 📊 集計リスト")
                if editor_data:
                    df = pd.DataFrame(editor_data)
                    edited = st.data_editor(
                        df,
                        column_config={
                            "No": st.column_config.NumberColumn(width="small", disabled=True),
                            "項目": st.column_config.TextColumn(width="medium"),
                            "値": st.column_config.TextColumn(width="small", disabled=True),
                            "単位": st.column_config.TextColumn(width="small", disabled=True),
                            "抜": st.column_config.CheckboxColumn(width="small"),
                            "🔍": st.column_config.LinkColumn(width="small", display_text="検索"),
                            "🔗 リンク": st.column_config.LinkColumn(width="medium", help="URL"),
                            "備考": st.column_config.TextColumn(width="large"),
                            "idx": None
                        },
                        hide_index=True,
                        key="data_editor"
                    )
                    
                    if not df.equals(edited):
                        for i, row in edited.iterrows():
                            idx = row["idx"]
                            st.session_state.history[idx]['label'] = row["項目"]
                            st.session_state.history[idx]['is_subtraction'] = row["抜"]
                            st.session_state.history[idx]['remarks'] = row["備考"]
                            st.session_state.history[idx]['link'] = row["🔗 リンク"]
                        st.rerun()

                    summary = {}
                    for i, item in enumerate(st.session_state.history):
                        val = 0
                        pts = item['points']
                        if item['type'] == 'dist':
                            d_px = 0
                            for j in range(len(pts)-1): d_px += calc_dist(pts[j], pts[j+1])
                            val = d_px * scale
                        elif item['type'] == 'area':
                            if len(pts) >= 3: val = calc_poly_area(pts) * (scale**2)
                        
                        if item.get('is_subtraction', False): val = -val
                        unit = "m" if item['type']=='dist' else "㎡"
                        k = f"{item['label']} ({unit})"
                        summary[k] = summary.get(k, 0) + val
                    
                    st.divider()
                    for k, v in summary.items():
                        c = "#d32f2f" if v < 0 else "#333"
                        v_str = f"▲ {abs(v):.2f}" if v < 0 else f"{v:.2f}"
                        st.markdown(f"**{k}**: <span style='color:{c}; font-size:1.1em;'>{v_str}</span>", unsafe_allow_html=True)
                    
                    csv = edited.drop(columns=["idx", "🔍"]).to_csv(index=False).encode('utf-8-sig')
                    st.download_button("CSV保存", csv, "sekisan.csv", "text/csv", use_container_width=True)
                else:
                    st.caption("データなし")
                st.markdown('</div>', unsafe_allow_html=True)

            else:
                st.info("👈 左でスケール設定してください")

    else:
        st.info("👈 左サイドバーから図面を読み込んでください")

if __name__ == "__main__":
    main()
