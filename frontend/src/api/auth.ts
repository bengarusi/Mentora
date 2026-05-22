import { apiClient } from "./client";
import type { LoginResponse, Student } from "../types";

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
  age: number;
  grade: string;
  math_level?: string;
  english_level?: string;
}

export async function register(payload: RegisterPayload): Promise<Student> {
  const { data } = await apiClient.post<Student>("/auth/register", payload);
  return data;
}

export async function login(
  email: string,
  password: string
): Promise<LoginResponse> {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  const { data } = await apiClient.post<LoginResponse>("/auth/login", form);
  return data;
}

export async function fetchMe(): Promise<Student> {
  const { data } = await apiClient.get<Student>("/auth/me");
  return data;
}
