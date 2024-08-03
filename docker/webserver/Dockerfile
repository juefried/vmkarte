# Use the official NGINX image as the base
FROM nginx:alpine

# Create a non-root user and group, only if they don't already exist
RUN addgroup -S nginx || true && adduser -S -G nginx nginx || true

# Set permissions for the nginx directories and files
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx /tmp /var/run

# Copy static files to the appropriate directory
COPY www_data /www_data

# Copy nginx server block configuration
COPY default.conf /etc/nginx/conf.d/default.conf

# Copy custom nginx.conf
COPY nginx.conf /etc/nginx/nginx.conf

# Set permissions for the copied files
RUN chown -R nginx:nginx /etc/nginx/conf.d/default.conf /etc/nginx/nginx.conf

# Switch to the non-root user
USER nginx

# Expose port 8080
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
