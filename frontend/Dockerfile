FROM node:20 as build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
# Update nginx to run on port 8080
RUN sed -i 's/listen  *80;/listen 8080;/g' /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# Handle client side routing
RUN sed -i '/index  index.html index.htm;/a \        try_files $uri $uri/ /index.html;' /etc/nginx/conf.d/default.conf
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
