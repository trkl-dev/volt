-- name: GetVolt :one
SELECT *
FROM volt
WHERE 
	volt.id = @id;

