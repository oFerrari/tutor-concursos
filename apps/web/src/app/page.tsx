"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

export default function PaginaInicial() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getToken() ? "/fila" : "/login");
  }, [router]);

  return null;
}
