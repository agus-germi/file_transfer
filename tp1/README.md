# Transferencia de Archivos Cliente-Servidor utilizando UDP

- Descripción del Proyecto

Este proyecto implementa un protocolo de aplicación para la transferencia de archivos utilizando el protocolo **UDP**. La arquitectura es cliente-servidor, y las operaciones principales soportadas son:

    - **UPLOAD**: Transferencia de un archivo desde el cliente hacia el servidor.
    - **DOWNLOAD**: Transferencia de un archivo desde el servidor hacia el cliente.

El protocolo garantiza la entrega confiable de archivos implementando dos versiones:
    - **Stop & Wait**
    - **Selective Acknowledgment (SACK)**

Además, se simulan condiciones de pérdida de paquetes usando **Mininet** para validar la robustez del protocolo.

- Requisitos
 (Agregar requisitos!)

    - Dependencias
        - **Python 3.x** 
        - **Librería estándar de sockets** (incluida en Python)
        - **Mininet** (para simular redes con pérdida de paquetes)
        - **flake8** (para cumplir con el estándar de codificación PEP8)

    - Instalación de flake8
        ```bash
        pip install flake8
        ```

    - Instalación de Mininet
        Puedes instalar Mininet siguiendo las instrucciones oficiales en [https://mininet.org/download/](https://mininet.org/download/).

- Ejecución del Servidor
    - Para iniciar el servidor, usa el siguiente comando:
        ``` bash
        python start-server -H <IP_SERVIDOR> -p <PUERTO> -s <DIRECTORIO_ALMACENAMIENTO> [-v | -q]
        ```

    - Argumentos:
        - -H, --host: Dirección IP del servidor.
        - -p, --port: Puerto del servidor.
        - -s, --storage: Directorio donde se almacenarán los archivos en el servidor.
        - -v, --verbose: Aumenta la verbosidad de la salida (opcional).
        - -q, --quiet: Disminuye la verbosidad de la salida (opcional).

    - Ejemplo:
        ```bash 
        python start-server -H 127.0.0.1 -p 5000 -s /tmp/server_files
        ```

- Ejecución del Cliente
    - Subida de Archivos **(UPLOAD)**
        - Para subir un archivo al servidor, ejecuta el siguiente comando:
            ```bash
            python upload -H <IP_SERVIDOR> -p <PUERTO> -s <RUTA_ARCHIVO_ORIGEN> -n <NOMBRE_ARCHIVO_DESTINO> [-v | -q]
            ```

        - Ejemplo:
            ```bash 
            python upload -H 127.0.0.1 -p 5000 -s ./file.txt -n file_on_server.txt
            ```

    - Descarga de Archivos **(DOWNLOAD)**
        - Para descargar un archivo desde el servidor, usa el siguiente comando:
            ```bash
            python download -H <IP_SERVIDOR> -p <PUERTO> -d <RUTA_ARCHIVO_DESTINO> -n <NOMBRE_ARCHIVO_SERVIDOR> [-v | -q]
            ```

        - Argumentos:
            - -H, --host: Dirección IP del servidor.
            - -p, --port: Puerto del servidor.
            - -s, --src: Ruta del archivo a subir desde el cliente (UPLOAD).
            - -d, --dst: Ruta donde se guardará el archivo descargado en el cliente (DOWNLOAD).
            - -n, --name: Nombre con el que se guardará el archivo en el servidor.
            - -v, --verbose: Aumenta la verbosidad de la salida (opcional).
            - -q, --quiet: Disminuye la verbosidad de la salida (opcional).
