# 阶段 1: 构建 (Build Stage)
FROM node:20 AS build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# 开始打包，生成 dist 文件夹
RUN npm run build

# 阶段 2: 生产环境 (Production Stage)
FROM nginx:stable-alpine as production-stage
# 把刚才生成的 dist 复制到 Nginx 目录
COPY --from=build-stage /app/dist /usr/share/nginx/html
# 把我们写的 nginx.conf 复制进去
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]