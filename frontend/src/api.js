import axios from 'axios';

const apiURL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const instance = axios.create({
  baseURL: apiURL,
});

export const workspaceApi = {
  create: (data) => instance.post('/workspaces', data).then(r => r.data),
  list: () => instance.get('/workspaces').then(r => r.data),
};

export const campaignApi = {
  create: (data) => instance.post('/campaigns', data).then(r => r.data),
  list: (workspaceId) => instance.get(`/campaigns?workspace_id=${workspaceId}`).then(r => r.data),
  get: (id) => instance.get(`/campaigns/${id}`).then(r => r.data),
};

export const prospectApi = {
  create: (data) => instance.post('/prospects', data).then(r => r.data),
  list: (campaignId) => instance.get(`/prospects?campaign_id=${campaignId}`).then(r => r.data),
  uploadCSV: (formData) => instance.post('/prospects/csv-upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    }
  }).then(r => r.data),
};

export const emailApi = {
  send: (data) => instance.post('/send-email', data).then(r => r.data),
  list: (params = {}) => instance.get('/emails', { params }).then(r => r.data),
  get: (id) => instance.get(`/emails/${id}`).then(r => r.data),
};

export const followupApi = {
  listPending: (workspaceId) => instance.get(`/followups/pending?workspace_id=${workspaceId}`).then(r => r.data),
  approve: (id, data) => instance.post(`/followups/${id}/approve`, data).then(r => r.data),
  reject: (id) => instance.post(`/followups/${id}/reject`).then(r => r.data),
};

export default instance;
