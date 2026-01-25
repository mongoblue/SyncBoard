export interface BoardColumn {
    id: string; // UUID 是字符串
    title: string;
    project: string; // 外键 ID 也是字符串
    position: number;
    // 预留给后续：前端展示时，列里面通常直接包含任务列表
    // tasks?: TaskCard[]; 
    tasks:TaskCard[];
}

export interface TaskCard {
    id: string; // UUID 是字符串
    column: string;
    title: string;
    content: string; // 对应后端的 content
    position: number;
    assignee? : number | null; // User ID 通常是自增 Int，如果是 UUID 则改为 string
}

export interface User{
    id:number;
    username:string;
}