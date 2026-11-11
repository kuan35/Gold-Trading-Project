import test from 'node:test';import assert from 'node:assert/strict';
import {freshReminderEvents} from '../src/ReminderNotifications';
test('notifications only show recent new durable events and reject duplicate, future or stale entries',()=>{
 const now=Date.parse('2026-11-04T00:00:00Z'),row=(id:string,delta:number)=>({id,name:'提醒',message:'已達條件',created_at_utc:new Date(now+delta).toISOString()});
 const result=freshReminderEvents([row('seen',-1000),row('old',-700000),row('new',-500),row('new',-500),row('future',6000)],new Set(['seen']),now);
 assert.deepEqual(result.map(r=>r.id),['new']);
});
import {reminderSources} from '../src/ReminderNotifications';
test('only the selected account environment polls reminders and each keeps a separate seen list',()=>{
 assert.deepEqual(reminderSources('demo').map(s=>s.enabled),[true,false]);
 const live=reminderSources('live');assert.deepEqual(live.map(s=>s.enabled),[false,true]);
 assert.equal(live[0].label,'DEMO · ');assert.equal(live[1].path,'/api/live/trading/alerts');assert.equal(live[1].label,'LIVE · ');
 assert.notEqual(live[0].key,live[1].key);
});
