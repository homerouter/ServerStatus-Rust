#!/usr/bin/env python3
"""
build_english_frontend.py - Build 100% English web frontend for ServerStatus-Rust.

Supports either:
1. In-place patching of the repository's web/ directory.
2. Downloading assets from a running ServerStatus instance, replacing Chinese UI strings,
   and outputting clean static files.
"""

import argparse
import os
import re
import sys
import urllib.request

TRANSLATIONS = [
    # Compound & detail modal strings (MUST COME FIRST before shorter substrings)
    (r"\u65f6\u5ef6(\u8054/\u7535/\u79fb):", "Latency (CU/CT/CM):"),
    (r"\u4e22\u5305(\u8054/\u7535/\u79fb):", "Loss (CU/CT/CM):"),
    (r"\u8054\u901a | \u7535\u4fe1 | \u79fb\u52a8", "CU | CT | CM"),
    (r"\u8fdb/\u7ebf:", "Process/Thread:"),
    (r"\u6700\u540e\u66f4\u65b0\uff1a", "Last Updated: "),
    (r"\u4ea4\u6362\u5206\u533a", "Swap"),
    (r"\u5904\u7406\u5668", "CPU"),
    (r"\u603b\u6d41\u91cf", "Total Traffic"),
    (r"\u6708\u6d41\u91cf", "Monthly Traffic"),
    # General labels
    (r"\u65f6\u5ef6", "Latency"),
    (r"\u786c\u76d8", "Disk"),
    (r"\u7535\u4fe1", "CT"),
    (r"\u7f51\u7edc", "Network"),
    (r"\u8282\u70b9", "Node"),
    (r"\u8054\u901a", "CU"),
    (r"\u9519\u8bef", "Error"),
    (r"\u5728\u7ebf", "Uptime"),
    (r"\u79fb\u52a8", "CM"),
    (r"\u4f4d\u7f6e", "Location"),
    (r"\u7c7b\u578b", "Type"),
    (r"\u5185\u5b58", "RAM"),
    (r"\u4e22\u5305", "Loss"),
    (r"\u534f\u8bae", "Protocol"),
    (r"\u8d1f\u8f7d", "Load"),
    # Catch-all for residual (联/电/移)
    (r"Latency(\u8054/\u7535/\u79fb):", "Latency (CU/CT/CM):"),
    (r"Loss(\u8054/\u7535/\u79fb):", "Loss (CU/CT/CM):"),
    (r"(\u8054/\u7535/\u79fb):", " (CU/CT/CM):"),
    (r"(\u8054/\u7535/\u79fb)", " (CU/CT/CM)"),
    ("Latency(\\u8054/\\u7535/\\u79fb):", "Latency (CU/CT/CM):"),
    ("Loss(\\u8054/\\u7535/\\u79fb):", "Loss (CU/CT/CM):"),
    ("(\\u8054/\\u7535/\\u79fb):", " (CU/CT/CM):"),
    ("(\\u8054/\\u7535/\\u79fb)", " (CU/CT/CM)"),
    ("(联/电/移):", " (CU/CT/CM):"),
    ("(联/电/移)", " (CU/CT/CM)"),
]

TAB_CSS = """
<style>
/* ServerStatus Fleet Tab Navigation */
.ssr-tab-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 12px;
  padding: 0 4px;
  flex-wrap: wrap;
}
.ssr-tab-btn {
  display: inline-flex;
  align-items: center;
  padding: 5px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease-in-out;
  border: 1px solid transparent;
  user-select: none;
}
.ssr-tab-btn-active {
  background-color: #4f46e5;
  color: #ffffff;
  border-color: #4338ca;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}
.ssr-tab-btn-inactive {
  background-color: #f1f5f9;
  color: #475569;
  border-color: #e2e8f0;
}
.ssr-tab-btn-inactive:hover {
  background-color: #e2e8f0;
  color: #1e293b;
}
.dark .ssr-tab-btn-active {
  background-color: #10b981;
  color: #0f172a;
  border-color: #059669;
  font-weight: 700;
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.25);
}
.dark .ssr-tab-btn-inactive {
  background-color: #334155;
  color: #cbd5e1;
  border-color: #475569;
}
.dark .ssr-tab-btn-inactive:hover {
  background-color: #3e4f68;
  color: #f8fafc;
}
.ssr-tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 8px;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 700;
  border-radius: 9999px;
  background-color: rgba(0, 0, 0, 0.15);
  line-height: 1.2;
}
.dark .ssr-tab-btn-active .ssr-tab-badge {
  background-color: rgba(0, 0, 0, 0.2);
  color: #0f172a;
}
.dark .ssr-tab-btn-inactive .ssr-tab-badge {
  background-color: rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
}
</style>
"""


def patch_content(html: str, js: str):
    html = html.replace("<title>ServerStatus-Rust</title>", "<title>Tailnet Fleet Status</title>")
    html = html.replace("探针,威力加强版,ServerStatus-Rust,ServerStatusRust,云探针", "Tailnet,ServerStatus,Fleet,Monitoring")
    html = html.replace("ServerStatus 探针 威力加强版 ServerStatus-Rust", "Tailnet Fleet Server Status Monitoring")
    html = re.sub(r'src="/static/js/main\.32884401\.js(\?v=[^"]*)?"', 'src="/static/js/main.32884401.js?v=20261013_tab"', html)
    html = re.sub(r'href="/static/css/main\.479df68b\.css(\?v=[^"]*)?"', 'href="/static/css/main.479df68b.css?v=20261013_tab"', html)
    if "</head>" in html and ".ssr-tab-bar" not in html:
        html = html.replace("</head>", f"{TAB_CSS}\n</head>")

    for src, dst in TRANSLATIONS:
        js = js.replace(src, dst)

    js = js.replace(
        "children:e.online4||e.online6?e.uptime:",
        "children:e.online4||e.online6?(e.uptime||\"\").replace(\" \\u5929\",\" days\").replace(\"\\u5929\",\"d\"):",
    )

    target_load = '(0,Be.jsx)("div",{className:"col-start-1 col-end-7 text-right",children:"Load:"}),'
    replacement_protocol_load = '(0,Be.jsx)("div",{className:"col-start-1 col-end-7 text-right",children:"Protocol:"}),(0,Be.jsxs)("div",{className:"col-start-7 col-end-13 text-left",children:["IPv4: ",e.online4?"Online 🟢":"Offline 🔴","  |  IPv6: ",e.online6?"Online 🟢":"Offline 🔴"]}),' + target_load
    if target_load in js:
        js = js.replace(target_load, replacement_protocol_load, 1)

    target_navbar = '(0,Be.jsx)("div",{className:"pr-8",children:(0,Be.jsx)(zb,{})})'
    replacement_navbar = '(0,Be.jsxs)("div",{className:"flex items-center gap-3 pr-4 sm:pr-8",children:[(0,Be.jsx)("a",{href:"/map",target:"_blank",rel:"noopener noreferrer",title:"World Map 🌍",className:"text-2xl hover:opacity-80 transition cursor-pointer select-none",children:"🌍"}),(0,Be.jsx)(zb,{})]})'
    if target_navbar in js:
        js = js.replace(target_navbar, replacement_navbar, 1)

    target_tupd = '[e.tcp_count,"/",e.udp_count,"/",e.process_count,"/",e.thread_count]'
    replacement_tupd = '[e.tcp_count>1e7?"-":e.tcp_count,"/",e.udp_count>1e7?"-":e.udp_count,"/",e.process_count,"/",e.thread_count>1e7?"-":e.thread_count]'
    if target_tupd in js:
        js = js.replace(target_tupd, replacement_tupd, 1)

    target_pw_table = (
        ',[a,o]=(0,e.useState)([]);return(0,Be.jsxs)("div",{className:"mx-auto min-w-min flex-1",children:[(0,Be.jsx)("div",{children:t.servers.length>0?(0,Be.jsxs)("table",{id:"ssr-table",'
    )
    replacement_pw_table = (
        ',[a,o]=(0,e.useState)([]),'
        '[tab,setTab]=(0,e.useState)(()=>{'
        'try{const h=window.location.hash.replace("#","");return["all","oracle","other"].includes(h)?h:"all"}catch(_){return"all"}'
        '});'
        'const isOther=s=>["ali","dc9"].includes((s.name||"").toLowerCase())||(s.labels&&s.labels.includes("group=other"));'
        'const sAll=t.servers||[];'
        'const sOracle=sAll.filter(s=>!isOther(s));'
        'const sOther=sAll.filter(s=>isOther(s));'
        'const sDisplay=tab==="oracle"?sOracle:(tab==="other"?sOther:sAll);'
        'const tabBtn=(k,lbl,cnt)=>(0,Be.jsxs)("button",{'
        'type:"button",'
        'onClick:()=>{setTab(k);o([]);try{window.location.hash=k}catch(_){}},'
        'className:"ssr-tab-btn "+(tab===k?"ssr-tab-btn-active":"ssr-tab-btn-inactive"),'
        'children:[lbl,(0,Be.jsx)("span",{className:"ssr-tab-badge",children:cnt})]'
        '},k);'
        'return(0,Be.jsxs)("div",{className:"mx-auto min-w-min flex-1",children:['
        '(0,Be.jsxs)("div",{className:"ssr-tab-bar",children:['
        'tabBtn("all","All Nodes",sAll.length),'
        'tabBtn("oracle","Oracle Cloud",sOracle.length),'
        'tabBtn("other","Ali & DC9",sOther.length)'
        ']}),'
        '(0,Be.jsx)("div",{children:sAll.length>0?(0,Be.jsxs)("table",{id:"ssr-table",'
    )
    if target_pw_table in js:
        js = js.replace(target_pw_table, replacement_pw_table, 1)

    target_tbody = '(0,Be.jsx)("tbody",{children:t.servers.map(((e,t)=>(0,Be.jsxs)(Be.Fragment,{children:'
    replacement_tbody = '(0,Be.jsx)("tbody",{children:sDisplay.map(((e,t)=>(0,Be.jsxs)(Be.Fragment,{children:'
    if target_tbody in js:
        js = js.replace(target_tbody, replacement_tbody, 1)

    return html, js


def patch_local_dir(web_dir: str):
    html_path = os.path.join(web_dir, "index.html")
    js_path = os.path.join(web_dir, "static/js/main.32884401.js")

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    html, js = patch_content(html, js)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"Patched local frontend directory: {web_dir}")


def build_from_url(base_url: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "static/js"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "static/css"), exist_ok=True)

    print(f"Fetching assets from {base_url}...")
    html_url = f"{base_url}/"
    with urllib.request.urlopen(html_url, timeout=10) as resp:
        html = resp.read().decode("utf-8")

    js_url = f"{base_url}/static/js/main.32884401.js"
    with urllib.request.urlopen(js_url, timeout=10) as resp:
        js = resp.read().decode("utf-8")

    html, js = patch_content(html, js)

    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(output_dir, "static/js/main.32884401.js"), "w", encoding="utf-8") as f:
        f.write(js)

    for rel_path in [
        "static/js/748.aa97738e.chunk.js",
        "static/css/main.479df68b.css",
        "favicon.png",
        "manifest.json",
        "logo192.svg",
    ]:
        try:
            with urllib.request.urlopen(f"{base_url}/{rel_path}", timeout=10) as resp:
                data = resp.read()
            dest_file = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            with open(dest_file, "wb") as f:
                f.write(data)
        except Exception as e:
            print(f"  ! Warning: could not download {rel_path}: {e}")

    print("Build complete in", output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build or patch English frontend for ServerStatus-Rust")
    parser.add_argument("source", nargs="?", default="", help="HTTP URL or path to web/ directory")
    parser.add_argument("output", nargs="?", default="", help="Output directory when downloading from URL")
    args = parser.parse_args()

    if not args.source:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        local_web = os.path.join(repo_root, "web")
        patch_local_dir(local_web)
    elif args.source.startswith("http://") or args.source.startswith("https://"):
        out = args.output if args.output else "/tmp/web_en"
        build_from_url(args.source, out)
    else:
        patch_local_dir(args.source)
