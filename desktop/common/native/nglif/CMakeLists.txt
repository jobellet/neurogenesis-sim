# nglif: portable integer LIF kernel of neurogenesis-sim (C11, no dependencies).
#   cmake -S desktop/common/native/nglif -B build/nglif && cmake --build build/nglif --config Release
#   ctest --test-dir build/nglif -C Release --output-on-failure        (golden fixtures in desktop/common/fixtures)
cmake_minimum_required(VERSION 3.16)
project(nglif VERSION 1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
if(MSVC)
  add_compile_options(/W4 /wd4996)
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_library(nglif STATIC nglif.c)
target_include_directories(nglif PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

add_library(nglif_shared SHARED nglif.c)
target_include_directories(nglif_shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_definitions(nglif_shared PRIVATE NGLIF_BUILD_DLL)
set_target_properties(nglif_shared PROPERTIES OUTPUT_NAME nglif)

add_executable(nglif_test nglif_test.c)
target_link_libraries(nglif_test nglif)

enable_testing()
add_test(NAME golden_fixtures COMMAND nglif_test ${CMAKE_CURRENT_SOURCE_DIR}/../../fixtures)
