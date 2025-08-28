"use client";
import { useState } from "react";
import TusUploader from "../TusUploader";
import { createMerge, getJob } from "@/app/lib/api";

export default function MergePanel() {
  const [video, setVideo] = useState<{name:string; tusUrl:string} | null>(null);
  const [audio, setAudio] = useState<{name:string; tusUrl:string} | null>(null);
  const [job, setJob] = useState<{id:string; state:string; result?:any} | null>(null);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="font-medium mb-2">Upload Video</div>
          <TusUploader multiple={false} onUploaded={(f)=>setVideo({name:f.name, tusUrl:f.tusUrl})}/>
        </div>
        <div>
          <div className="font-medium mb-2">Upload Audio</div>
          <TusUploader multiple={false} onUploaded={(f)=>setAudio({name:f.name, tusUrl:f.tusUrl})}/>
        </div>
      </div>
      <button
        disabled={!video || !audio}
        onClick={async ()=>{
          const { task_id } = await createMerge(video!.tusUrl, audio!.tusUrl, 0);
          setJob({ id: task_id, state: "PENDING" });
          while (true) {
            const s = await getJob(task_id);
            if (s.state !== "PENDING" && s.state !== "STARTED") { setJob({ id: task_id, state: s.state, result: s.result }); break; }
            await new Promise(r => setTimeout(r, 1200));
          }
        }}
        className="px-4 py-2 rounded-xl bg-indigo-600 text-white disabled:opacity-60"
      >
        Merge
      </button>

      {job && (
        <div className="p-3 rounded-lg border">
          <div>Status: {job.state}</div>
          {job.result?.result?.url && <a className="underline" href={job.result.result.url} target="_blank">Download merged.mp4</a>}
        </div>
      )}
    </div>
  );
}
