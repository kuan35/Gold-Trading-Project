export const caseReviewScope=(snapshotId:string,caseRef?:string)=>JSON.stringify([snapshotId,caseRef??null]);
export const matchingCaseReview=(value:{snapshot_id:string;case_ref?:string|null},snapshotId:string,caseRef?:string)=>value.snapshot_id===snapshotId&&(value.case_ref??null)===(caseRef??null);
export const casePreviewUrl=(snapshotId:string,caseRef?:string)=>`/assistant/snapshots/${encodeURIComponent(snapshotId)}/case-preview`+(caseRef?`?case_ref=${encodeURIComponent(caseRef)}`:'');
