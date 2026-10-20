ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY gallery-backend/ /app/src/backend/middlewares/user/
