import { defineConfig } from 'vitepress'

export default defineConfig({

  title: 'AuroraView',
  description: 'A lightweight WebView framework for DCC software',
  
  base: '/auroraview/',
  
  head: [
    ['link', { rel: 'icon', type: 'image/png', href: '/auroraview/logo.png' }]
  ],

  locales: {
    root: {
      label: 'English',
      lang: 'en',
    },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      themeConfig: {
        nav: [
          { text: '首页', link: '/zh/' },
          { text: '官网与示例', link: 'https://try-auroraview.github.io/zh/' },
          { text: '指南', link: '/zh/guide/getting-started' },
          { text: 'API', link: '/zh/api/' },
          { text: 'DCC 集成', link: '/zh/dcc/' },
        ],
        sidebar: {
          '/zh/guide/': [
            {
              text: '入门',
              items: [
                { text: '快速开始', link: '/zh/guide/getting-started' },
                { text: '安装', link: '/zh/guide/installation' },
                { text: '统一 API', link: '/zh/guide/unified-api' },
                { text: '架构概述', link: '/zh/guide/architecture' },
                { text: '设计思路', link: '/zh/guide/design-philosophy' },
              ]
            },
            {
              text: '核心概念',
              items: [
                { text: 'WebView 基础', link: '/zh/guide/webview-basics' },
                { text: '双向通信', link: '/zh/guide/communication' },
                { text: 'UI 与 Agent 工具契约', link: '/zh/guide/dcc-mcp' },
                { text: '自定义协议', link: '/zh/guide/custom-protocol' },
                { text: 'TypeScript SDK', link: '/zh/guide/typescript-sdk' },
              ]
            },
            {
              text: '高级功能',
              items: [
                { text: '高级用法', link: '/zh/guide/advanced-usage' },
                { text: '应用打包', link: '/zh/guide/packing' },
                { text: 'CLI 参考', link: '/zh/guide/cli' },
                { text: '性能优化', link: '/zh/guide/performance' },
                { text: 'Qt 集成', link: '/zh/guide/qt-integration' },
                { text: '本地资源加载', link: '/zh/guide/local-resources' },
                { text: '自定义右键菜单', link: '/zh/guide/context-menu' },
                { text: '文件拖放', link: '/zh/guide/file-drop' },
                { text: 'Headless 测试', link: '/zh/guide/headless-testing' },
                { text: 'AI Agent 与 CDP', link: '/zh/guide/ai-agent-cdp' },
                { text: '系统托盘', link: '/zh/guide/system-tray' },
                { text: '浮动面板', link: '/zh/guide/floating-panel' },
                { text: '子窗口系统', link: '/zh/guide/child-windows' },
                { text: '窗口特效', link: '/zh/guide/window-effects' },
              ]
            },
            {
              text: '展示',
              items: [
                { text: 'Gallery', link: '/zh/guide/gallery' },
                { text: '示例', link: '/zh/guide/examples' },
              ]
            },
            {
              text: 'Chrome 扩展兼容',
              items: [
                { text: 'Chrome API 兼容性', link: '/zh/guide/chrome-extension-apis' },
              ]
            },
            {
              text: '贡献',
              items: [
                { text: '贡献指南', link: '/zh/guide/contributing' },
              ]
            }
          ],
          '/zh/dcc/': [
            {
              text: 'DCC 集成',
              items: [
                { text: '概述', link: '/zh/dcc/' },
                { text: 'Maya', link: '/zh/dcc/maya' },
                { text: 'Houdini', link: '/zh/dcc/houdini' },
                { text: '3ds Max', link: '/zh/dcc/3dsmax' },
                { text: 'Blender', link: '/zh/dcc/blender' },
                { text: 'Photoshop', link: '/zh/dcc/photoshop' },
                { text: 'Unreal Engine', link: '/zh/dcc/unreal' },
              ]
            }
          ],
          '/zh/api/': [
            {
              text: 'API 参考',
              items: [
                { text: '概述', link: '/zh/api/' },
                { text: 'WebView', link: '/zh/api/webview' },
                { text: 'QtWebView', link: '/zh/api/qt-webview' },
                { text: 'AuroraView', link: '/zh/api/auroraview' },
              ]
            }
          ]
        }
      }
    }
  },

  themeConfig: {
    logo: '/logo.png',
    
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Website & Examples', link: 'https://try-auroraview.github.io/' },
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'API', link: '/api/' },
      { text: 'DCC Integration', link: '/dcc/' },
      {
        text: 'Links',
        items: [
          { text: 'GitHub', link: 'https://github.com/try-auroraview/auroraview' },
          { text: 'PyPI', link: 'https://pypi.org/project/auroraview/' },
          { text: 'Changelog', link: 'https://github.com/try-auroraview/auroraview/blob/main/CHANGELOG.md' },
        ]
      }
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Getting Started',
          items: [
            { text: 'Quick Start', link: '/guide/getting-started' },
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Unified API', link: '/guide/unified-api' },
            { text: 'Architecture', link: '/guide/architecture' },
            { text: 'Design Philosophy', link: '/guide/design-philosophy' },
          ]
        },
        {
          text: 'Core Concepts',
          items: [
            { text: 'WebView Basics', link: '/guide/webview-basics' },
            { text: 'Communication', link: '/guide/communication' },
            { text: 'Shared UI and agent tools', link: '/guide/dcc-mcp' },
            { text: 'Custom Protocol', link: '/guide/custom-protocol' },
            { text: 'TypeScript SDK', link: '/guide/typescript-sdk' },
          ]
        },
        {
          text: 'Advanced',
          items: [
            { text: 'Advanced Usage', link: '/guide/advanced-usage' },
            { text: 'Packing', link: '/guide/packing' },
            { text: 'CLI Reference', link: '/guide/cli' },
            { text: 'Performance', link: '/guide/performance' },
            { text: 'Qt Integration', link: '/guide/qt-integration' },
            { text: 'Local Resources', link: '/guide/local-resources' },
            { text: 'Context Menu', link: '/guide/context-menu' },
            { text: 'Headless Testing', link: '/guide/headless-testing' },
            { text: 'AI Agent & CDP', link: '/guide/ai-agent-cdp' },
            { text: 'System Tray', link: '/guide/system-tray' },
            { text: 'Floating Panel', link: '/guide/floating-panel' },
            { text: 'Child Windows', link: '/guide/child-windows' },
            { text: 'Window Effects', link: '/guide/window-effects' },
          ]
        },
        {
          text: 'Showcase',
          items: [
            { text: 'Gallery', link: '/guide/gallery' },
            { text: 'Examples', link: '/guide/examples' },
          ]
        },
        {
          text: 'Chrome Extension',
          items: [
            { text: 'Chrome API Compatibility', link: '/guide/chrome-extension-apis' },
          ]
        },
        {
          text: 'Contributing',
          items: [
            { text: 'Contributing Guide', link: '/guide/contributing' },
          ]
        }
      ],
      '/dcc/': [
        {
          text: 'DCC Integration',
          items: [
            { text: 'Overview', link: '/dcc/' },
            { text: 'Maya', link: '/dcc/maya' },
            { text: 'Houdini', link: '/dcc/houdini' },
            { text: '3ds Max', link: '/dcc/3dsmax' },
            { text: 'Blender', link: '/dcc/blender' },
            { text: 'Photoshop', link: '/dcc/photoshop' },
            { text: 'Unreal Engine', link: '/dcc/unreal' },
          ]
        }
      ],
      '/api/': [
        {
          text: 'API Reference',
          items: [
            { text: 'Overview', link: '/api/' },
            { text: 'WebView', link: '/api/webview' },
            { text: 'QtWebView', link: '/api/qt-webview' },
            { text: 'AuroraView', link: '/api/auroraview' },
          ]
        }
      ]
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/try-auroraview/auroraview' }
    ],

    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2024-present Hal Long'
    },

    search: {
      provider: 'local'
    },

    editLink: {
      pattern: 'https://github.com/try-auroraview/auroraview/edit/main/docs/:path',
      text: 'Edit this page on GitHub'
    }
  }
})
