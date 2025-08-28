"use client";
import { useEffect, useRef } from "react";
import Uppy from "@uppy/core";
import Tus from "@uppy/tus";
import { getTusEndpoint } from "@/app/lib/api";

export default function TusUploader({ onUploaded }: { onUploaded: (tusUrl: string, name: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    (async () => {
      const tus = await getTusEndpoint();
      console.log("Tus endpoint:", tus);
    })();
  }, []);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const tus = await getTusEndpoint();
    const uppy = new Uppy({ autoProceed: true }).use(Tus, { endpoint: tus, chunkSize: 5 * 1024 * 1024 });
    const files = Array.from(e.target.files || []);
    for (const f of files) {
      uppy.addFile({ name: f.name, type: f.type, data: f });
    }
    uppy.on("upload-success", (file, resp) => {
      onUploaded(resp.uploadURL, file.name);
    });
    e.currentTarget.value = "";
  }

  return (
    <div className="p-4 border rounded-xl text-center">
      <input ref={inputRef} type="file" multiple onChange={onPick} />
    </div>
  );
}
