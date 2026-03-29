import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 120000,
});

export async function checkHealth() {
  const { data } = await axios.get("/health", { baseURL: "" });
  return data;
}

export const topics = {
  list: () => client.get("/topics").then((r) => r.data),
  create: (body) => client.post("/topics", body).then((r) => r.data),
  update: (id, body) => client.patch(`/topics/${id}`, body).then((r) => r.data),
  remove: (id) => client.delete(`/topics/${id}`),
  referenceImageUrl: (id) => `/api/topics/${id}/reference-image`,
  uploadReferenceImage: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return client.post(`/topics/${id}/reference-image`, fd).then((r) => r.data);
  },
  deleteReferenceImage: (id) => client.delete(`/topics/${id}/reference-image`).then((r) => r.data),
  refinePreview: (body) => client.post("/topics/refine-preview", body).then((r) => r.data),
};

export const content = {
  list: (params) => client.get("/content", { params }).then((r) => r.data),
  get: (id) => client.get(`/content/${id}`).then((r) => r.data),
  patch: (id, body) => client.patch(`/content/${id}`, body).then((r) => r.data),
  remove: (id) => client.delete(`/content/${id}`),
  downloadImageUrl: (id) => `/api/content/${id}/download/image`,
  downloadVideoUrl: (id) => `/api/content/${id}/download/video`,
  downloadBlogZipUrl: (id) => `/api/content/${id}/download/blog`,
  diagramUrl: (id, index) => `/api/content/${id}/blog/diagram/${index}`,
  batchZip: (ids, includeVideo) =>
    client
      .post(
        "/content/download/batch",
        { ids, include_video: includeVideo },
        { responseType: "blob" }
      )
      .then((r) => r.data),
  blogSections: (id) => client.get(`/content/${id}/blog/sections`).then((r) => r.data),
  revise: (id, body) => client.post(`/content/${id}/revise`, body).then((r) => r.data),
  refreshCaption: (id) => client.post(`/content/${id}/caption/refresh`).then((r) => r.data),
};

export const generation = {
  generate: (body) => client.post("/generate", body).then((r) => r.data),
  blog: (topic_id) => client.post("/generate/blog", { topic_id }).then((r) => r.data),
  quote: (topic_id) => client.post("/generate/quote", { topic_id }).then((r) => r.data),
  image: (content_item_id) =>
    client.post("/generate/image", { content_item_id }).then((r) => r.data),
};

export const jobs = {
  get: (id) => client.get(`/jobs/${id}`).then((r) => r.data),
  list: (params) => client.get("/jobs", { params }).then((r) => r.data),
};

export const platforms = {
  list: () => client.get("/platforms").then((r) => r.data),
  accounts: () => client.get("/accounts").then((r) => r.data),
  addAccount: (body) => client.post("/accounts", body).then((r) => r.data),
  removeAccount: (id) => client.delete(`/accounts/${id}`),
  post: (body) => client.post("/post", body).then((r) => r.data),
  history: (params) => client.get("/post-history", { params }).then((r) => r.data),
};

export const settings = {
  get: () => client.get("/settings").then((r) => r.data),
  patch: (body) => client.patch("/settings", body).then((r) => r.data),
  llmModels: () => client.get("/llm/models").then((r) => r.data),
};
