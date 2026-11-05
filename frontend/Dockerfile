# The chat page is plain HTML, CSS and JavaScript: nginx serves the folder as it is (no build step)
# and forwards /api to the backend (nginx.conf), so js/config.js keeps apiBaseUrl "".
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/
COPY css /usr/share/nginx/html/css
COPY js /usr/share/nginx/html/js
COPY brand /usr/share/nginx/html/brand
EXPOSE 80
