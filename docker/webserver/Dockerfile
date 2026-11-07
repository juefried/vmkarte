# Use the official NGINX image as the base
FROM nginx:alpine

# Create a non-root user and group, only if they don't already exist
RUN addgroup -S nginx || true && adduser -S -G nginx nginx || true

# Set permissions for the nginx directories and files
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx /tmp /var/run

# Copy static files to the appropriate directory
COPY www_data /www_data

# Generate the public version metadata from the maintained VERSION file.
# APP_VERSION and BUILD_DATE can be overridden at build time.
ARG APP_VERSION=
ARG BUILD_DATE=
# Visible title and PWA name. The defaults keep the productive appearance.
ARG APP_TITLE=Velomobil-Forum Karte
ARG APP_SHORT_NAME=VMKarte

# Default for the productive setup. The test deployment overrides this at
# runtime with its public hostname.
ENV SERVER_NAME=_

RUN set -e; \
    if [ -z "$APP_VERSION" ]; then APP_VERSION=$(cat /www_data/VERSION); fi; \
    if [ -z "$APP_VERSION" ]; then echo "APP_VERSION is empty" >&2; exit 1; fi; \
    BUILD_DATE="${BUILD_DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"; \
    printf '{"version":"%s","buildDate":"%s"}\n' "$APP_VERSION" "$BUILD_DATE" > /www_data/app-version.json; \
    printf 'export const APP_VERSION = "%s";\nexport const BUILD_DATE = "%s";\n' "$APP_VERSION" "$BUILD_DATE" > /www_data/js/version.js; \
    sed -i "s|<title>Velomobil-Forum Karte</title>|<title>${APP_TITLE}</title>|" /www_data/karte.html; \
    sed -i "s|content=\"VMKarte\"|content=\"${APP_SHORT_NAME}\"|" /www_data/karte.html; \
    sed -i "s|\"name\": \"Velomobil-Forum Karte\"|\"name\": \"${APP_TITLE}\"|" /www_data/manifest.webmanifest; \
    sed -i "s|\"short_name\": \"VMKarte\"|\"short_name\": \"${APP_SHORT_NAME}\"|" /www_data/manifest.webmanifest

# Put the server block into the nginx template directory so SERVER_NAME can be
# provided at container start instead of being baked into the image.
COPY default.conf /etc/nginx/templates/default.conf.template
RUN rm -f /etc/nginx/conf.d/default.conf && \
    sed -i 's/server_name _;/server_name ${SERVER_NAME};/' /etc/nginx/templates/default.conf.template

# Copy custom nginx.conf and shared security headers
COPY nginx.conf /etc/nginx/nginx.conf
COPY security-headers.conf /etc/nginx/security-headers.conf

# Set permissions for the copied files
RUN chown -R nginx:nginx /etc/nginx

# Switch to the non-root user
USER nginx

# Expose port 8080
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
