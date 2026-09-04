ARG BASE_IMAGE=bpatrik/pigallery2:latest@sha256:d7a61b6daa410537064d4f661122545bc4d9b16cd91a3862d654c3555cb63992
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="PiGallery2 with named GPX waypoints"
LABEL org.opencontainers.image.description="PiGallery2 3.5.2 frontend with named, described, color-coded GPX waypoint markers"

COPY build/dist/ /app/dist/
