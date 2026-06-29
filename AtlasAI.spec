# AtlasAI.spec — PyInstaller spec for Atlas AI
# Works for both Windows (.exe) and macOS (.app → .dmg)

import sys, os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Collect all data for heavy packages
datas = []
binaries = []
hiddenimports = []

# geopandas + shapely + fiona need special handling
for pkg in ['geopandas', 'shapely', 'fiona', 'pyproj', 'pandas', 'matplotlib', 'flask', 'flask_cors']:
    d, b, h = collect_all(pkg)
    datas    += d
    binaries += b
    hiddenimports += h

# Include hidden submodules
hiddenimports += collect_submodules('flask')
hiddenimports += collect_submodules('jinja2')
hiddenimports += collect_submodules('werkzeug')
hiddenimports += [
    'routes.chat_routes',
    'routes.map_routes',
    'routes.project_routes',
    'routes.study_routes',
    'routes.file_routes',
    'routes.provider_routes',
    'services.command_router',
    'services.intent_router',
    'services.tool_definitions',
    'services.provider_manager',
    'services.map_context_engine',
    'services.geography_normalizer',
    'services.geo_matcher',
    'services.graph_dispatcher',
    'services.graph_generators.bar_graph',
    'services.graph_generators.line_graph',
    'services.graph_generators.scatter_plot',
    'services.graph_generators.pie_chart',
    'services.graph_generators.treemap',
    'services.graph_generators.heatmap',
    'services.graph_generators.area_graph',
    'services.graph_generators.bubble_chart',
    'services.graph_generators.radar_chart',
    'services.graph_generators.gantt_chart',
    'services.graph_generators.box_plot',
    'services.graph_generators.histogram',
    'services.graph_generators.pareto_chart',
    'services.graph_generators.waterfall_chart',
    'services.graph_generators.dot_plot',
    'services.graph_generators.candlestick_chart',
    'utils.llm',
    'utils.map_generator',
    'utils.data_parser',
    'utils.storage',
    'utils.execution_state',
]

# Bundle: backend assets + frontend static files + config
datas += [
    ('backend/assets',  'assets'),           # GeoJSON
    ('frontend',        'frontend'),         # HTML/CSS/JS
    ('backend/config',  'config'),           # providers.json, api_keys.json
]

a = Analysis(
    ['launcher.py'],                         # entry point (see launcher.py)
    pathex=['backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='Atlas AI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                           # no terminal window
    
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Atlas AI',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='Atlas AI.app',
    
    bundle_identifier='com.atlasai.lms',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '2.0.0',
        'CFBundleVersion': '2.0.0',
        'NSRequiresAquaSystemAppearance': False,
    },
)
