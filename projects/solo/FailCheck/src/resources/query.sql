/*
Скрипт определяющий актуальный список failed в перегрузках PXF
*/
with backup as (
	select objects_name, max(date_start) as date_start
		from logs_backup_all_schedule
		where scripts = 'PXF'
		group by objects_name
)
, table_group as (
	select table_name, max(date_start) as date_start 
		from s_grnplm_ld_blago_ubhq_in.{0}
		where status ='FAILED'
		group by table_name
)
, fight_table as (
	select pxf1.* 
		from s_grnplm_ld_blago_ubhq_in.{0} pxf1
		join table_group pxf2
			on pxf1.table_name = pxf2.table_name 
			and pxf1.date_start =pxf2.date_start 
		where pxf1.status ='FAILED'

)

select  table_name, 
		status, 
		date_start, 
		date_end, 
		'Полный лог ошибки в таблице s_grnplm_ld_blago_ubhq_in.logs_pxf_table' as logs_info 
		from fight_table pxf
		where not exists  (select * from backup where pxf.table_name=backup.objects_name and pxf.date_start<=backup.date_start)
;


/*
Скрипт определяющий актуальный список failed в перегрузках Procedure
*/
with backup as (
	select objects_name, max(date_start) as date_start
		from logs_backup_all_schedule
		where scripts = 'PROCEDURE'
		group by objects_name
)
, table_group as (
	select procedure_name, max(date_start) as date_start 
		from s_grnplm_ld_blago_ubhq_in.{0}
		where status ='FAILED'
		group by procedure_name
)
, fight_table as (
	select proc1.* 
		from s_grnplm_ld_blago_ubhq_in.{0} proc1
		join table_group proc2
			on proc1.procedure_name = proc2.procedure_name 
			and proc1.date_start =proc2.date_start 
		where proc1.status ='FAILED'

)

select  procedure_name, 
		status, 
		date_start, 
		date_end, 
		'Полный лог ошибки в таблице s_grnplm_ld_blago_ubhq_in.logs_procedure' as logs_info 
		from fight_table proc
		where not exists  (select * from backup where proc.procedure_name=backup.objects_name and proc.date_start<=backup.date_start)
;