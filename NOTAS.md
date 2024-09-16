## Init del cliente:
- ip
- puerto
- Protocolo elegido -> DUDA: como se que protocolo usa ?
- Accion (Download - Upload)

## FORMATO PAQUETE:
- nro de secuencia
- flags:
    1) para indicar el fin -> para indicar el fin de la transaccion y cerrar socket
    2) Data type:
        - data type 1) paquete ACK -> DUDA : teniendo esto y el nro d secuencia, es necesario un nro de ACK ??
        - data type 2) paquete de datos
- datos
- id cliente ? o algo que identifique al tipo de cliente ?

## INICIALIZACION de la conexión

El cliente le manda el init al servidor y espera por el ACK de ese init, 
una vez recibido entonces el cliente comienza a mandar -> UPLOAD
El cliente le manda el init al servidor,
y espera a que el servidor le empiece a mandar cosas -> DOWNLOAD









