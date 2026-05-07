from __future__ import annotations

from pathlib import Path
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "storage"
DOWNLOAD_DIR = BASE_DIR / "downloads"

# Windows 文件名非法字符
ILLEGAL_FILE_CHARS = '<>:"/\\|?*'

CNINFO_HOME = "https://www.cninfo.com.cn"
CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_BASE = "https://static.cninfo.com.cn/"

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.cninfo.com.cn",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

# 业务分类 -> 巨潮 category 参数映射（部分分类在接口侧可能会共享编码）
CATEGORY_MAP = {
    "年报": "category_ndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "三季报": "category_sjdbg_szsh",
    "业绩预告": "category_yjygjxz_szsh",
    "权益分派": "category_qyfpxzcs_szsh",
    "董事会": "category_dshgg_szsh",
    "监事会": "category_jshgg_szsh",
    "股东会": "category_gddh_szsh",
    "日常经营": "category_rcjy_szsh",
    "公司治理": "category_gszl_szsh",
    "中介报告": "category_zj_szsh",
    "首发": "category_sf_szsh",
    "增发": "category_zf_szsh",
    "股权激励": "category_gqjl_szsh",
    "配股": "category_pg_szsh",
    "解禁": "category_jj_szsh",
    "公司债": "category_gszq_szsh",
    "可转债": "category_kzzq_szsh",
    "其他融资": "category_qtrz_szsh",
    "股权变动": "category_gqbd_szsh",
    "补充更正": "category_bcgz_szsh",
    "澄清致歉": "category_cqzx_szsh",
    "风险提示": "category_fxts_szsh",
    "特别处理和退市": "category_tbclts_szsh",
    "退市整理期": "category_tszlq_szsh",
}

CATEGORY_ORDER = [
    "年报",
    "半年报",
    "一季报",
    "三季报",
    "业绩预告",
    "权益分派",
    "董事会",
    "监事会",
    "股东会",
    "日常经营",
    "公司治理",
    "中介报告",
    "首发",
    "增发",
    "股权激励",
    "配股",
    "解禁",
    "公司债",
    "可转债",
    "其他融资",
    "股权变动",
    "补充更正",
    "澄清致歉",
    "风险提示",
    "特别处理和退市",
    "退市整理期",
]

PLATE_ORDER = [
    "深市",
    "创业板",
    "沪主板",
    "深主板",
    "沪市",
    "科创板",
    "北交所",
]

PLATE_MAP = {
    "深市": "sz",
    "沪市": "sh",
    "北交所": "bj",
    "深主板": "szmb",
    "沪主板": "shmb",
    "创业板": "szcy",
    "科创板": "shkcp",
}
