FROM --platform=$BUILDPLATFORM node:24-alpine AS frontend-builder

WORKDIR /src/frontend

RUN npm install --global pnpm@10.24.0

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm run build


FROM --platform=$BUILDPLATFORM golang:1.25-alpine AS backend-builder

ARG APP_VERSION
ARG GIT_COMMIT
ARG TARGETOS
ARG TARGETARCH

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . ./
COPY --from=frontend-builder /src/frontend/dist ./frontend/dist

RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build \
    -ldflags="-s -w -X github.com/filebrowser/filebrowser/v2/version.Version=${APP_VERSION} -X github.com/filebrowser/filebrowser/v2/version.CommitSHA=${GIT_COMMIT}" \
    -o /out/filebrowser .


FROM alpine:3.23 AS runtime-assets

RUN apk add --no-cache ca-certificates mailcap tini-static && \
    wget -O /JSON.sh https://raw.githubusercontent.com/dominictarr/JSON.sh/0d5e5c77365f63809bf6e77ef44a1f34b0e05840/JSON.sh


FROM busybox:1.37.0-musl

ENV UID=1000
ENV GID=1000

RUN addgroup -g "$GID" user && \
    adduser -D -u "$UID" -G user user

COPY --chown=user:user --from=backend-builder /out/filebrowser /bin/filebrowser
COPY --chown=user:user docker/common/ /
COPY --chown=user:user docker/alpine/ /
COPY --chown=user:user --from=runtime-assets /sbin/tini-static /bin/tini
COPY --from=runtime-assets /JSON.sh /JSON.sh
COPY --from=runtime-assets /etc/ca-certificates.conf /etc/ca-certificates.conf
COPY --from=runtime-assets /etc/ca-certificates /etc/ca-certificates
COPY --from=runtime-assets /etc/mime.types /etc/mime.types
COPY --from=runtime-assets /etc/ssl /etc/ssl

RUN mkdir -p /config /database /srv && \
    chown -R user:user /config /database /srv && \
    chmod +x /healthcheck.sh

HEALTHCHECK --start-period=2s --interval=5s --timeout=3s CMD /healthcheck.sh

USER user

VOLUME /srv /config /database

EXPOSE 80

ENTRYPOINT ["tini", "--", "/init.sh"]
