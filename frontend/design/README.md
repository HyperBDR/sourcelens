# 设计文档静态页面

存放纯静态的设计稿 / 原型页面（HTML/CSS/JS），用于开发期评审。

## 访问方式

仅在 **dev 模式** 下可访问：

```bash
cd frontend && npm run dev
# 打开 http://localhost:3000/design/
```

由 `vite.config.js` 中的 `designPagesPlugin`（`apply: 'serve'`）提供静态服务，
目录位于 `src/`、`public/` 之外，因此 `npm run build` 生产构建不会包含这些页面。

## 添加新页面

1. 把 HTML 文件放进本目录，例如 `login.html`。
2. 在 `index.html` 的列表里加一条链接，例如：
   ```html
   <li><a href="/design/login.html">登录页设计</a></li>
   ```
3. 浏览器访问 `http://localhost:3000/design/login.html`。
