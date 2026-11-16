# Implementación del perfil de GitHub

## Cambios para revisión

- El README abre en inglés con experiencia, capacidades en Markdown y enlaces al perfil profesional en inglés y español y a los servicios en español. La presentación identifica el sector salud en términos generales.
- El barco conserva su animación, la lista de visitantes en ambos temas y el botón para solicitar un contenedor. La biblioteca plegable conserva los 15 enlaces de la versión anterior.
- `perfil/perfil.py` y `perfil/perfil.json` regeneran solo la biblioteca. Las imágenes que presentaban el rol y el supuesto nivel de inglés se sustituyeron por texto actual en el README.
- `puerto/puerto.py` y `perfil/libreria.py` asignan nombres a los archivos a partir de su contenido y cada generador actualiza su propio bloque. Los cambios en los bloques y sus recursos se pueden revisar en conjunto.
- Los workflows del puerto y del perfil publican artefactos de revisión con un `revision.patch`. Los permisos de escritura de contenido e issues se retiraron.

## Cómo revisar actualizaciones

1. Busca la ejecución en Actions y descarga el artefacto. El README muestra el resultado, y el parche incluye altas y bajas de archivos generados.
2. Desde una rama basada en el `main` actualizado, ejecuta `git apply --check revision.patch`. Si pasa, aplica el parche y revisa el diff antes de hacer un commit personal.
3. Si otro contenedor ya se publicó desde el mismo punto de partida, prepara de nuevo la solicitud sobre el estado actualizado. En PowerShell, usa `$env:USUARIO = '<usuario-de-GitHub>'` y ejecuta `python puerto/puerto.py cargar` con Pillow disponible. Cada solicitud se puede marcar como atendida después de publicar el cambio.

## Ajustes de cuenta pendientes de autorización

- Bio propuesta. `Full-stack engineer | React, TypeScript, Node.js & Python | Web apps, APIs and automation | Venezuela · UTC-4`
- Enlace web propuesto. `https://portfolio-eosin-theta-40.vercel.app`
- En el perfil público usa **Edit profile** para bio y enlace. Usa **Customize your pins** para conservar **Portfolio** primero y considerar **Ordo** y **Puerto Vivo**. La revisión previa registró Portfolio como único pin. Los candidatos son repositorios públicos propios incluidos en el README.
- Conservar el avatar ilustrado actual. Cuando estén desplegadas las rutas, abrir `/career`, `/perfil` y `/servicios` desde el README y comprobar ambos CV antes de publicar la rama del perfil.

## Verificación local

- `python -m unittest discover -s tests -v` ejecuta la biblioteca y el render WebP/SVG del puerto dos veces con datos fijos y sin acceso de red. Verifica el contenido fuera de cada bloque, los enlaces y la igualdad de archivos tras regenerar. También prueba que un README sin marcadores preserve sus recursos anteriores.
- Se comprobó que los recursos locales referidos existen, que se mantuvieron las 15 URLs de la biblioteca y que los workflows cargan como YAML con permisos de lectura.
- Queda verificar en GitHub el render visual y la ejecución real de Actions después de autorizar la publicación. Las tres rutas del portafolio deben validarse en su despliegue.
