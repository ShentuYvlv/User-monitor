FROM node:18-alpine

WORKDIR /app

# 复制依赖文件
COPY package.json yarn.lock ./

# 安装依赖 (包括 ts-node 等开发依赖，因为我们要直接运行 ts 文件或构建)
# 为了简单起见，我们安装所有依赖
RUN yarn install

# 复制源码
COPY . .

# 暴露端口
EXPOSE 3000

# 启动命令 (使用 ts-node 直接运行 server.ts，或者先 build 再 run)
# 这里为了开发方便，直接用 ts-node
CMD ["yarn", "server"]
