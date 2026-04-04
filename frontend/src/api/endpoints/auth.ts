import { apiClient } from '../client';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface UserInfo {
  id: number;
  username: string;
  full_name: string | null;
  email: string | null;
  is_admin: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

export const login = async (data: LoginRequest): Promise<LoginResponse> => {
  const response = await apiClient.post<LoginResponse>('/auth/login', data);
  return response.data;
};

export const getMe = async (): Promise<UserInfo> => {
  const response = await apiClient.get<UserInfo>('/auth/me');
  return response.data;
};
